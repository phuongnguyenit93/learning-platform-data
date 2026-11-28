# Kiểm tra rủi ro khi mở package quá rộng cho mọi thư viện

## 1. Vì sao mở package quá rộng là rủi ro?

Java Platform Module System (JPMS) dùng ranh giới module và package để kiểm soát phần nào của một module được mã bên ngoài sử dụng. Một số framework cần reflection sâu để ánh xạ object, tạo proxy, tuần tự hóa dữ liệu hoặc inject dependency. Khi gặp lỗi truy cập, cách sửa nhanh thường thấy là thêm `--add-opens ...=ALL-UNNAMED`.

Tùy chọn này có thể làm ứng dụng chạy tiếp, nhưng phạm vi quyền được mở lớn hơn nhiều so với một thư viện cụ thể. `ALL-UNNAMED` có nghĩa là mọi unnamed module, thường là toàn bộ mã trên classpath, đều được phép deep reflection vào package được chỉ định. Điều đó bao gồm cả dependency bắc cầu, plugin và mã được nạp về sau.

Mở package rộng có thể:

- Cho phép nhiều thư viện đọc hoặc thay đổi trạng thái private mà chúng không cần biết.
- Làm lộ dữ liệu nội bộ như token, mật khẩu, cấu hình hoặc trạng thái đối tượng.
- Khiến ứng dụng phụ thuộc vào tên field, cấu trúc class và chi tiết triển khai không phải API công khai.
- Tạo thêm điểm gãy khi nâng JDK hoặc cập nhật framework.
- Làm suy yếu khả năng kiểm soát ranh giới giữa các module.

Mục tiêu của bài là xác định đúng package và đúng module cần reflection, hiểu phạm vi của từng tùy chọn, rồi thu hẹp quyền mở theo từng thư viện. Đây là kiến thức vẫn cần thiết khi vận hành ứng dụng Java hiện đại.

## 2. Phân biệt exports và opens

`exports` và `opens` giải quyết hai nhu cầu khác nhau:

| Cơ chế | Truy cập được cấp | Phạm vi |
| --- | --- | --- |
| `exports package.name` | Mã bên ngoài dùng các kiểu `public` và thành viên `public`/`protected` của chúng theo quy tắc truy cập Java | Compile time và runtime; reflection thông thường trên API được export |
| `opens package.name` | Reflection sâu vào mọi kiểu và thành viên trong package, kể cả private | Runtime; không cấp quyền truy cập khi biên dịch |
| `exports package.name to module.name` | Export có giới hạn cho module được nêu | Compile time và runtime |
| `opens package.name to module.name` | Mở reflection sâu cho module được nêu | Runtime |

Một package được export không đồng nghĩa mọi thư viện có thể truy cập private field. Khi framework cần gọi `setAccessible(true)`, `MethodHandles.privateLookupIn` hoặc thao tác tương tự trên thành viên không public, package phải được mở cho module của framework.

Ngược lại, `opens` không giúp source code biên dịch được khi đang tham chiếu trực tiếp tới một kiểu không được export. Trong trường hợp cần dùng kiểu public của package chưa export, phải xem xét API công khai hoặc `--add-exports`, không dùng `--add-opens` để thay thế.

## 3. Strong encapsulation trong các JDK hiện đại

JPMS được giới thiệu từ Java 9. JDK 16 chuyển sang strong encapsulation mặc định đối với phần lớn API nội bộ của JDK theo JEP 396. Từ JDK 17, JEP 403 tiếp tục mạnh hóa việc đóng gói các thành phần nội bộ; ứng dụng không thể dựa vào quyền truy cập phản chiếu rộng như thời Java cũ.

Điều này có nghĩa:

- Package không export hoặc open sẽ chặn truy cập từ module khác theo quy tắc JPMS.
- Reflection vào private member của package JDK bị đóng gói có thể thất bại với `InaccessibleObjectException`.
- Các thư viện dựa vào chi tiết nội bộ của JDK cần được nâng cấp hoặc thay thế bằng API được hỗ trợ.

Không dùng `--illegal-access` như một giải pháp hiện hành. Từ JDK 17, tùy chọn chuyển tiếp này không còn mở lại quyền truy cập; dùng nó chỉ tạo cảnh báo và không giải quyết lỗi. Khi thật sự cần tương thích tạm thời, xác định package và module cụ thể rồi đánh giá `--add-opens` hoặc `--add-exports` đúng mục đích.

## 4. Cú pháp và phạm vi của --add-opens

Cú pháp:

~~~text
--add-opens <source-module>/<package>=<target-module>(,<target-module>)*
~~~

Ví dụ:

~~~powershell
java --add-opens=java.base/java.lang=com.example.json -m com.example.app/com.example.app.Main
~~~

Trong ví dụ:

- `java.base` là module chứa package cần mở.
- `java.lang` là package được mở.
- `com.example.json` là module được phép reflection sâu vào package đó.

Tên ở vế phải phải là tên module thực tế, không phải tên file JAR hoặc tên artifact Maven/Gradle. Có thể xác định module name từ descriptor của thư viện hoặc metadata module tương ứng.

Có thể mở package cho nhiều module bằng danh sách phân cách dấu phẩy:

~~~text
--add-opens=java.base/java.lang=com.example.json,com.example.orm
~~~

Chỉ mở các package thực sự cần và chỉ cho các module thực sự gọi reflection. Có thể khai báo nhiều tùy chọn `--add-opens` riêng biệt để từng package có phạm vi rõ ràng.

## 5. Vì sao ALL-UNNAMED quá rộng?

Ví dụ:

~~~powershell
java --add-opens=java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

`ALL-UNNAMED` là đích đặc biệt đại diện cho mọi unnamed module. Mã trên classpath được đặt trong unnamed module của class loader tương ứng. Vì vậy, tùy chọn này có thể cấp deep reflection cho nhiều thư viện trên classpath, không chỉ thư viện gây ra lỗi ban đầu. Nó cũng áp dụng cho unnamed module được tạo sau khi JVM khởi động.

Rủi ro thực tế:

1. Một thư viện JSON có thể cần đọc field của model, nhưng một dependency khác trên classpath cũng nhận được quyền vào package được mở.
2. Một plugin được nạp sau đó cũng có thể dùng quyền này mà không cần được liệt kê riêng.
3. Thư viện có thể bắt đầu phụ thuộc vào field private của JDK hoặc module ứng dụng. Khi cấu trúc nội bộ thay đổi, ứng dụng có thể lỗi dù API công khai vẫn tương thích.
4. Mã có quyền deep reflection có thể đọc hoặc thay đổi trạng thái private không thuộc hợp đồng công khai của lớp.

`ALL-UNNAMED` không có nghĩa mọi named module đều được mở. Tuy vậy, trong ứng dụng classpath có nhiều dependency, đây thường là phạm vi rất lớn. Không thêm nó vào cấu hình production chỉ để làm biến mất một lỗi reflection mà chưa xác định thư viện gây lỗi.

## 6. Phân biệt --add-exports và --add-opens

Hai tùy chọn thường bị dùng nhầm:

| Tùy chọn | Dùng khi | Không giải quyết |
| --- | --- | --- |
| `--add-exports source/package=target` | Mã cần truy cập kiểu public trong package chưa export, kể cả API nội bộ | Không cấp quyền reflection sâu vào private member |
| `--add-opens source/package=target` | Framework cần reflection sâu vào package ở runtime | Không cho phép source code tham chiếu trực tiếp kiểu chưa export khi biên dịch |

Ví dụ `--add-exports`:

~~~powershell
javac --add-exports java.management/com.sun.jmx.remote.internal=com.example.app -d out src\com\example\app\Main.java
~~~

Ví dụ `--add-opens`:

~~~powershell
java --add-opens=java.base/java.lang=com.example.legacyjson -m com.example.app/com.example.app.Main
~~~

`--add-exports` có thể được dùng ở compile time và runtime. `--add-opens` là cấu hình runtime cho reflection. Nếu thư viện cần truy cập private member, thêm `--add-exports` thường không khắc phục được nguyên nhân.

Truy cập API nội bộ của JDK bằng `--add-exports` vẫn tạo phụ thuộc không được bảo đảm tương thích. Ưu tiên API Java SE được hỗ trợ hoặc phiên bản thư viện đã thay thế internal API.

## 7. Mở package có giới hạn trong module-info.java

Nếu bạn sở hữu module chứa model và framework là named module, khai báo qualified opens trong module descriptor:

~~~java
module com.example.domain {
    exports com.example.domain.api;

    opens com.example.domain.model to com.example.orm;
}
~~~

Ở đây:

- Package API được export để mã ứng dụng dùng kiểu công khai.
- Chỉ package model được mở cho module ORM.
- Các package khác vẫn được đóng gói theo mặc định.

Đây thường là lựa chọn rõ ràng hơn so với mở toàn bộ module. Nếu framework chạy trên classpath, module descriptor không thể dùng `ALL-UNNAMED` như một tên module thông thường; khi đó cần đánh giá tùy chọn runtime `--add-opens` và hiểu rằng nó mở cho mọi unnamed module.

Tránh khai báo:

~~~java
open module com.example.domain {
    // ...
}
~~~

`open module` mở tất cả package của module cho reflection ở runtime. Nếu chỉ một framework cần truy cập package model, mở toàn module là rộng hơn nhu cầu.

## 8. Automatic module cũng ảnh hưởng encapsulation

Một JAR không có `module-info.class` khi đặt trên module path có thể trở thành automatic module. Theo quy tắc JPMS, automatic module được xử lý như thể tất cả package của nó được export và open ở runtime.

Điều này hữu ích cho quá trình chuyển đổi thư viện sang module path, nhưng không tạo ra ranh giới encapsulation chặt như explicit module. Vì vậy:

- Không coi automatic module là bằng chứng rằng package đã được thiết kế thành API ổn định.
- Không để package nội bộ trở thành hợp đồng mà module khác phụ thuộc lâu dài.
- Khi kiểm soát được thư viện, cân nhắc bổ sung explicit module descriptor và chỉ export/opens các package cần thiết.

Automatic module không tự mở package của module JDK khác. Nó chỉ có quy tắc export/open rộng đối với package thuộc chính automatic module đó.

## 9. Kiểm tra lỗi reflection trước khi thêm quyền mở

Ví dụ một thư viện cũ cố truy cập private field trong `java.lang.String`:

~~~java
import java.lang.reflect.Field;

public class ReflectionProbe {
    public static void main(String[] args) throws Exception {
        Field field = String.class.getDeclaredField("value");

        if (!field.trySetAccessible()) {
            System.out.println("Package is not open to this module");
            return;
        }

        System.out.println("Deep reflection is available");
    }
}
~~~

Đây là probe minh họa cho ranh giới module, không phải cách xử lý chuỗi nên dùng trong ứng dụng. Trên JDK hiện đại, `trySetAccessible()` có thể trả về `false` vì `java.base/java.lang` không mở cho module gọi. Gọi `setAccessible(true)` trong trường hợp bị chặn có thể ném `InaccessibleObjectException`.

Khi gặp lỗi:

1. Đọc đầy đủ stack trace và xác định class nào thực hiện reflection.
2. Xác định module chứa class đó: named module hay unnamed module trên classpath.
3. Xác định package nguồn thực sự bị chặn.
4. Kiểm tra thư viện có phiên bản mới dùng API công khai hay không.
5. Chỉ thử mở package trong môi trường test để xác nhận nguyên nhân; chưa đưa tùy chọn rộng vào production.

Đừng suy luận rằng mọi `IllegalAccessException` đều cần `--add-opens`. Lỗi có thể đến từ modifier Java, module không đọc module khác, package chưa export, package chưa open hoặc chính sách truy cập khác.

## 10. Rủi ro khi framework đọc và sửa private state

Reflection sâu thường cần cho ORM, serializer, dependency injection, proxy hoặc mapper. Tuy nhiên, mở package cho framework đồng nghĩa framework có thể quan sát các thành viên nội bộ trong package đó.

Các hệ quả cần đánh giá:

- **Dữ liệu nhạy cảm:** field private có thể chứa thông tin xác thực, token hoặc dữ liệu cá nhân. Một framework/plugin không cần truy cập vẫn có thể nhận quyền nếu nằm trong cùng phạm vi mở.
- **Bất biến đối tượng:** framework có thể thay đổi trạng thái mà constructor hoặc method công khai vốn kiểm soát.
- **Phụ thuộc implementation:** thư viện dựa vào tên field, kiểu field hoặc cấu trúc class cụ thể.
- **Nâng cấp khó:** thay đổi nội bộ của JDK hoặc module ứng dụng có thể làm reflection thất bại.
- **Tăng bề mặt lỗi:** nhiều thư viện được phép deep reflection khiến việc tìm nguồn truy cập và đánh giá tác động phức tạp hơn.

JPMS là cơ chế encapsulation và kiểm soát truy cập giữa module, không phải sandbox bảo mật hoàn chỉnh. Mở package không thay thế phân quyền hệ điều hành, kiểm soát plugin hoặc cách ly tiến trình. Dù vậy, mở package quá rộng vẫn làm giảm đáng kể khả năng giới hạn truy cập nội bộ trong JVM.

## 11. Lưu ý riêng về final field trên JDK 26

Mở package cho deep reflection không đồng nghĩa được phép tùy ý ghi mọi field. Từ JDK 26, việc sửa `final` instance field qua deep reflection phát cảnh báo khi lần đầu xảy ra trong module. JDK dự kiến sẽ chặn hành vi này trong một bản phát hành tương lai.

`--add-opens` một mình không cấp quyền ghi final field. JDK 26 có cơ chế riêng `--enable-final-field-mutation` và `--illegal-final-field-mutation`; việc sửa final field vẫn cần package được mở và module thực hiện phải được cho phép theo chính sách riêng. Các field final không thể sửa theo quy tắc của reflection, chẳng hạn static final, field của record và hidden class, vẫn bị giới hạn.

Nếu JDK 26 phát cảnh báo về final field mutation:

- Xác định module và thư viện gây mutation.
- Ưu tiên nâng cấp hoặc thay thế thư viện để không sửa final field sau khởi tạo.
- Dùng `--illegal-final-field-mutation=debug` trong môi trường kiểm thử để lấy stack trace tìm nguồn mutation.
- Không thêm `--enable-final-field-mutation=ALL-UNNAMED` như một cách sửa chung cho toàn bộ classpath.

Không dùng `--add-opens` với kỳ vọng khôi phục mọi hành vi reflection cũ. Encapsulation và final field integrity là hai lớp hạn chế có liên quan nhưng có cơ chế riêng.

## 12. Phân tích dependency và tìm thư viện cần nâng cấp

`jdeps` có thể phát hiện tham chiếu tĩnh tới JDK internal API:

~~~powershell
jdeps --jdk-internals --class-path "lib\*" app.jar
~~~

Hoặc kiểm tra từng thư viện:

~~~powershell
jdeps --jdk-internals lib\legacy-library.jar
~~~

Kết quả giúp xác định dependency tới package nội bộ như các package `sun.*` hoặc API JDK không được hỗ trợ. Sau khi xác định, tìm phiên bản thư viện đã chuyển sang API công khai.

Giới hạn của `jdeps`:

- Công cụ phân tích dependency tĩnh trong bytecode.
- Không thể phát hiện đầy đủ tên class/package được ghép động rồi truyền cho `Class.forName`.
- Không thể kết luận mọi lời gọi `setAccessible`, `privateLookupIn` hoặc reflection runtime có thành công hay không.
- Không thay thế integration test trên JDK mục tiêu.

Vì vậy, kết hợp `jdeps` với log lỗi reflection, tìm kiếm trong source/dependency và test các chức năng ORM, JSON, serialization, proxy hoặc plugin.

## 13. Quy trình thu hẹp package được mở

Áp dụng quy trình sau khi một thư viện báo lỗi truy cập:

1. **Nhận diện bên gọi:** ghi lại class, module, phiên bản thư viện và stack trace.
2. **Xác định package nguồn:** lấy chính xác module/package xuất hiện trong thông báo lỗi.
3. **Kiểm tra mục đích:** thư viện cần API public, internal API hay deep reflection vào private member?
4. **Nâng cấp trước:** kiểm tra phiên bản thư viện mới đã loại bỏ truy cập nội bộ hay chưa.
5. **Chọn cơ chế đúng:** dùng API công khai; nếu cần public internal type thì đánh giá `--add-exports`; nếu cần deep reflection thì đánh giá `opens` có giới hạn.
6. **Thu hẹp target:** ưu tiên named module cụ thể; chỉ dùng `ALL-UNNAMED` khi consumer thực sự ở classpath và chấp nhận phạm vi mọi unnamed module.
7. **Kiểm thử:** chạy test trên JDK thấp nhất và JDK mục tiêu phát hành, bao gồm test khởi động và test tính năng gây reflection.
8. **Ghi nhận ngoại lệ:** lưu package, module consumer, thư viện, lý do, người phụ trách và điều kiện loại bỏ cấu hình mở.
9. **Rà soát định kỳ:** sau khi nâng cấp thư viện, thử bỏ `--add-opens` hoặc qualified `opens` để xác nhận còn cần hay không.

Ví dụ cấu hình tạm thời cho một module cụ thể:

~~~powershell
java --add-opens=java.base/java.lang=com.example.legacyjson -m com.example.app/com.example.app.Main
~~~

Khi framework đã nâng cấp và không còn cần truy cập package đó, xóa tùy chọn. Không giữ cấu hình mở chỉ vì nó đã tồn tại lâu trong script khởi chạy.

## 14. Checklist đánh giá cấu hình production

- Có xác định được thư viện và class thực hiện reflection không?
- Có phiên bản thư viện mới không cần truy cập JDK internals không?
- Có dùng nhầm `--add-exports` và `--add-opens` không?
- Package mở có đúng package tối thiểu không?
- Target là named module cụ thể hay `ALL-UNNAMED`?
- Nếu dùng `ALL-UNNAMED`, đã đánh giá toàn bộ dependency/plugin trên classpath chưa?
- Có đang dùng `open module` hoặc automatic module khiến nhiều package được mở hơn dự kiến không?
- Có kiểm thử trên JDK hiện đại với đúng launcher options không?
- Có kiểm tra cảnh báo final field mutation trên JDK 26 không?
- Có kế hoạch loại bỏ từng ngoại lệ mở package sau khi nâng thư viện không?

**Ghi nhớ:** `--add-opens` là quyền deep reflection ở runtime. Mở cho `ALL-UNNAMED` có thể cấp quyền cho toàn bộ mã trên classpath, kể cả dependency và plugin được nạp sau. Ưu tiên API công khai, nâng cấp thư viện, hoặc qualified `opens`/`--add-opens` cho đúng module cần thiết. Không dùng `--illegal-access` đã mất tác dụng từ JDK 17; và trên JDK 26, không nhầm mở package với quyền sửa `final` field.

## Nguồn tham khảo chính thức

- [JEP 396: Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/396)
- [JEP 403: Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403)
- [Migrating from JDK 8 to Later JDK Releases — JDK 26](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html)
- [ModuleDescriptor API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/ModuleDescriptor.html)
- [Module API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Module.html)
- [The jdeps Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [Preparing for final Field Mutation Restrictions — JDK 26](https://docs.oracle.com/en/java/javase/26/migrate/preparing-final-field-mutation-restrictions.html)
