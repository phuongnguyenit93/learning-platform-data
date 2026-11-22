# Không cấp add-opens rộng hơn nhu cầu

Java Platform Module System (JPMS) cho phép module công khai API qua exports và mở package cho deep reflection qua opens. Khi một framework cần đọc field private hoặc gọi method không public, ứng dụng đôi khi phải bổ sung quyền mở package bằng khai báo module hoặc tùy chọn runtime --add-opens.

Quyền mở package có ảnh hưởng trực tiếp tới encapsulation. Nếu mở toàn bộ module hoặc dùng ALL-UNNAMED trong khi chỉ một framework cụ thể cần truy cập, phạm vi quyền được cấp sẽ lớn hơn yêu cầu thực tế.

Nguyên tắc nên áp dụng là **least privilege**: chỉ mở đúng package, cho đúng module cần dùng, trong đúng môi trường và trong thời gian cần thiết. --add-opens nên là một ngoại lệ có lý do, có chủ sở hữu và có kế hoạch loại bỏ.

## 1. --add-opens giải quyết vấn đề gì?

Trong JPMS, khai báo exports công khai các kiểu public của package cho module khác. Khai báo opens cho phép module được chỉ định thực hiện deep reflection vào package, bao gồm những member không public khi các điều kiện truy cập còn lại được đáp ứng.

Ví dụ:

~~~java
module com.example.account {
    exports com.example.account.api;

    opens com.example.account.model
        to com.example.orm;
}
~~~

Ở đây:

- com.example.account.api là API thông thường mà module khác có thể sử dụng nếu có readability.
- com.example.account.model được mở cho module com.example.orm để ORM có thể thực hiện deep reflection.
- Các package khác của com.example.account vẫn được đóng theo quy tắc module.
- Việc mở model không làm package đó trở thành API công khai để consumer import và sử dụng tùy ý.

Nếu không thể sửa module descriptor của module nguồn, có thể bổ sung quyền mở lúc khởi động JVM:

~~~shell
java \
  --module-path mods \
  --add-opens com.example.account/com.example.account.model=com.example.orm \
  --module com.example.app/com.example.app.Main
~~~

Cú pháp tổng quát:

~~~text
--add-opens <source-module>/<package>=<target-module>(,<target-module>)*
~~~

Trong đó:

- source-module là module sở hữu package cần mở.
- package là tên package đầy đủ, phân biệt chữ hoa và chữ thường.
- target-module là module được phép deep reflection vào package đó.
- Có thể chỉ định nhiều target module, phân cách bằng dấu phẩy.

Tùy chọn này được áp dụng ở runtime. Nó không thay đổi file module-info.java trong JAR và không thay thế cấu hình dependency khi biên dịch.

## 2. Phân biệt exports, opens và --add-opens

Ba cơ chế này có phạm vi khác nhau:

| Cơ chế | Quyền được cấp | Trường hợp sử dụng |
| --- | --- | --- |
| exports package | Truy cập các kiểu và member public theo quy tắc Java | Công khai API cho consumer |
| opens package | Deep reflection vào package từ module được phép | Framework cần ánh xạ field, constructor hoặc method không public |
| --add-opens | Bổ sung quyền opens lúc khởi động JVM | Tương thích thư viện cũ hoặc môi trường chưa thể sửa module descriptor |

Ví dụ package được export:

~~~java
module com.example.account {
    exports com.example.account.api;
}
~~~

Consumer có thể sử dụng public API trong package này nếu module consumer đọc được com.example.account. Việc export không tự động cho phép truy cập private field bằng reflection.

Ví dụ package được mở có giới hạn:

~~~java
module com.example.account {
    opens com.example.account.persistence
        to com.example.orm;
}
~~~

Module com.example.orm có thể thực hiện deep reflection vào package persistence theo quy tắc JPMS. Module khác không được hưởng quyền mở này chỉ vì package đã mở cho ORM.

Tùy chọn --add-exports không tương đương --add-opens. --add-exports hỗ trợ truy cập API public của package; --add-opens dành cho deep reflection. Nếu lỗi là InaccessibleObjectException khi framework truy cập private member, thêm --add-exports thường không giải quyết đúng nguyên nhân.

## 3. Chọn đúng phạm vi package và module đích

Giả sử ORM chỉ cần truy cập model của module account. Có ba cách cấu hình với phạm vi khác nhau:

~~~java
// Mở đúng package cho đúng module framework.
opens com.example.account.model to com.example.orm;
~~~

~~~shell
# Tương đương ở thời điểm chạy, không sửa module-info.java.
--add-opens com.example.account/com.example.account.model=com.example.orm
~~~

~~~java
// Phạm vi rộng hơn: mở toàn bộ package trong module.
open module com.example.account {
}
~~~

Nếu chỉ một package cần reflection, open module là quá rộng. Mọi package trong module sẽ được mở cho deep reflection theo quy tắc JPMS, khiến các chi tiết nội bộ khác cũng có thể bị framework hoặc code trong module được phép quan sát.

Tương tự, không nên mở nhiều package chỉ vì một lỗi ban đầu. Hãy xác định package thực sự chứa class hoặc member mà framework cần truy cập, rồi cấp quyền cho đúng module gọi.

Nếu framework gồm nhiều module riêng biệt, hãy xác định module nào thực sự thực hiện reflection. Đừng mặc định module facade hoặc module ứng dụng là caller. Có thể dùng class của framework tại call site để kiểm tra:

~~~java
Module frameworkModule = OrmRuntime.class.getModule();
Module domainModule = Account.class.getModule();

System.out.println(
    "Framework reads domain: "
        + frameworkModule.canRead(domainModule)
);

System.out.println(
    "Domain opens model to framework: "
        + domainModule.isOpen(
            "com.example.account.model",
            frameworkModule
        )
);
~~~

canRead kiểm tra quan hệ readability từ module framework tới module domain. isOpen được gọi trên module sở hữu package và nhận module framework làm đối số. Readability và opens là hai điều kiện riêng biệt; một điều kiện không tự tạo ra điều kiện còn lại.

## 4. Cẩn trọng với ALL-UNNAMED

Một số framework cũ chạy trên classpath và thuộc unnamed module. Trong trường hợp đó, target có thể là ALL-UNNAMED:

~~~shell
java \
  --module-path mods \
  --class-path libs/legacy-orm.jar \
  --add-opens com.example.account/com.example.account.model=ALL-UNNAMED \
  --module com.example.app/com.example.app.Main
~~~

ALL-UNNAMED là selector đặc biệt đại diện cho tất cả unnamed modules, bao gồm các unnamed module được tạo trong tương lai. Nó không chỉ đại diện cho một JAR hoặc một class loader duy nhất.

Vì thế:

- Nếu framework là named module, hãy chỉ định tên module cụ thể.
- Chỉ dùng ALL-UNNAMED khi caller thực sự thuộc unnamed module.
- Kiểm tra các thư viện trên classpath vì chúng có thể cùng nhận quyền mở package.
- Tránh dùng ALL-UNNAMED như một cách khắc phục chung cho mọi lỗi reflection.

Ví dụ sau mở toàn bộ package java.lang của JDK cho tất cả unnamed modules:

~~~shell
--add-opens java.base/java.lang=ALL-UNNAMED
~~~

Phạm vi này lớn hơn rất nhiều so với việc mở một package của ứng dụng cho một framework cụ thể. Chỉ sử dụng khi có yêu cầu tương thích được xác định rõ và đã đánh giá ảnh hưởng.

## 5. Xác định package nào thực sự cần mở

Không nên thêm --add-opens chỉ vì một thư viện báo lỗi chung chung. Hãy lấy class, package và module từ stack trace hoặc thông báo lỗi.

Một lỗi thường gặp:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field private ... accessible:
module com.example.account does not "opens
com.example.account.model" to module com.example.orm
~~~

Thông báo này cung cấp ba thông tin quan trọng:

1. Module nguồn: com.example.account.
2. Package cần mở: com.example.account.model.
3. Module đích đang yêu cầu quyền: com.example.orm.

Từ đó có thể cấu hình đúng một package và một target:

~~~shell
--add-opens com.example.account/com.example.account.model=com.example.orm
~~~

Nếu thông báo nói package không được mở cho unnamed module, hãy kiểm tra framework có đang chạy từ classpath hay không trước khi dùng ALL-UNNAMED.

Đối với code do mình kiểm soát, có thể kiểm tra trạng thái module mà không mở quyền:

~~~java
Module source = Account.class.getModule();
Module target = OrmRuntime.class.getModule();

boolean readable = target.canRead(source);
boolean open = source.isOpen(
    "com.example.account.model",
    target
);

System.out.println("Readable: " + readable);
System.out.println("Open: " + open);
~~~

Đoạn kiểm tra chỉ quan sát trạng thái hiện hành. Nó không thay đổi module graph và không mở package.

## 6. Phân biệt kiểm tra quyền với bật quyền reflection

Reflection API có một số phương thức dễ bị nhầm lẫn:

- canAccess(target) kiểm tra caller hiện tại có thể truy cập member hay không theo trạng thái hiện tại.
- trySetAccessible() thử bật cờ override. Nếu thành công, trạng thái truy cập của đối tượng AccessibleObject sẽ thay đổi.
- setAccessible(true) yêu cầu bật cờ override và có thể ném InaccessibleObjectException nếu module không cho phép.

Ví dụ kiểm tra một field:

~~~java
Field field = Account.class.getDeclaredField("secret");
Account account = new Account();

boolean accessibleNow = field.canAccess(account);
System.out.println("Accessible now: " + accessibleNow);
~~~

canAccess phù hợp khi chỉ muốn quan sát khả năng truy cập hiện tại. Nếu integration test cần xác nhận framework có thể bật deep reflection, có thể gọi trySetAccessible() trong một fixture được kiểm soát:

~~~java
boolean enabled = field.trySetAccessible();

if (!enabled) {
    throw new IllegalStateException(
        "The package is not open to this module"
    );
}
~~~

Lưu ý rằng trySetAccessible() không phải phép kiểm tra thuần túy: khi trả về true, nó đã bật quyền truy cập cho đối tượng field đó. Chỉ dùng trong test hoặc luồng thực sự cần truy cập member. Không dùng setAccessible(true) như một bước chẩn đoán mặc định.

## 7. Ưu tiên cấu hình module descriptor cho thiết kế dài hạn

Nếu sở hữu module nguồn, nên cân nhắc khai báo qualified opens thay vì phụ thuộc vào cờ runtime:

~~~java
module com.example.account {
    exports com.example.account.api;

    opens com.example.account.persistence
        to com.example.orm;
}
~~~

Ưu điểm:

- Quyền mở được ghi cùng module sở hữu package.
- Reviewer có thể thấy package nào được mở và cho module nào.
- Cấu hình đi cùng artifact, giảm phụ thuộc vào script khởi động.
- Phạm vi quyền có thể được quản lý như một phần của module design.

Qualified opens cũng làm rõ quan hệ tích hợp: module account chủ động cho phép module ORM truy cập sâu vào persistence model.

Tuy nhiên, không phải mọi package nội bộ đều nên mở. Chỉ mở những package có nhu cầu thực tế, chẳng hạn package chứa entity hoặc DTO mà framework cần ánh xạ.

Nếu framework không cần deep reflection, hãy dùng constructor, accessor, public API hoặc cơ chế mapping được thiết kế rõ ràng. Điều này giúp giảm sự phụ thuộc vào cấu trúc field nội bộ và giúp implementation dễ thay đổi hơn.

## 8. Dùng --add-opens như giải pháp tương thích có thời hạn

Trong ứng dụng legacy, có thể chưa thể sửa module descriptor hoặc nâng cấp framework ngay. Khi đó --add-opens là một cách tương thích ở runtime.

Nên quản lý nó theo các bước:

1. Ghi lại lỗi gốc và package cần mở.
2. Xác định chính xác module gọi reflection.
3. Thêm một cặp source module/package và target module.
4. Chạy kiểm thử tích hợp để xác nhận framework hoạt động.
5. Ghi chú lý do và dependency nào đang cần quyền mở.
6. Tạo công việc nâng cấp framework hoặc chuyển sang API không cần deep reflection.
7. Loại bỏ cờ khi dependency đã được sửa hoặc module descriptor đã khai báo opens phù hợp.

Không nên đưa các cờ mở rộng quyền vào biến môi trường dùng chung cho mọi ứng dụng nếu chỉ một dịch vụ cần chúng. Hãy đặt trong cấu hình khởi động của đúng tiến trình và môi trường.

Ví dụ cấu hình có ghi chú:

~~~shell
# Temporary compatibility for legacy ORM.
# Remove after upgrading ORM to a version that does not
# require deep reflection into the persistence package.
--add-opens com.example.account/com.example.account.persistence=com.example.orm
~~~

Cờ runtime nên được review như một thay đổi quyền truy cập. Nếu không còn cần thiết, hãy xóa nó thay vì để lại vô thời hạn.

## 9. Lưu ý với JDK internals

Từ JDK 17, JEP 403 tăng cường strong encapsulation đối với các internal APIs của JDK. Một số framework cũ có thể cố truy cập package nội bộ của JDK bằng reflection và nhận lỗi truy cập.

Ví dụ một cờ mở package cụ thể:

~~~shell
--add-opens java.base/java.lang=com.example.legacy
~~~

Đây là quyền mở package java.lang trong module java.base cho module com.example.legacy. Nó không phải giấy phép để truy cập tùy ý mọi internal API của JDK.

Không nên mở toàn bộ package JDK hoặc cấp cho ALL-UNNAMED chỉ để làm mất thông báo lỗi. Hãy ưu tiên:

- Nâng cấp framework lên phiên bản hỗ trợ JDK đang dùng.
- Sử dụng API được JDK công khai.
- Xóa dependency vào internal implementation của JDK.
- Nếu chưa thể nâng cấp ngay, chỉ mở đúng package cho đúng module và ghi nhận thời hạn loại bỏ.

Tùy chọn --illegal-access từng được dùng trong giai đoạn chuyển tiếp JPMS nhưng không còn là cách khôi phục quyền truy cập trên JDK 17 trở lên. Không nên dựa vào nó để xử lý lỗi encapsulation hiện tại.

## 10. Kiểm tra cấu hình trước khi phát hành

Trước khi triển khai ứng dụng có --add-opens, hãy kiểm tra:

1. Package được mở có đúng là package trong thông báo lỗi không?
2. Source module có đúng là module sở hữu class không?
3. Target module có đúng là module thực hiện reflection không?
4. Có thể dùng qualified opens trong module-info.java thay cho cờ runtime không?
5. Có thể thay reflection bằng public API, constructor hoặc accessor không?
6. Nếu dùng ALL-UNNAMED, có thật sự cần mở cho tất cả unnamed modules không?
7. Cờ có bị áp dụng ngoài tiến trình hoặc môi trường cần thiết không?
8. Có kiểm thử xác nhận tính năng hoạt động với phạm vi quyền nhỏ nhất không?
9. Có tài liệu về dependency và kế hoạch loại bỏ cờ không?

Có thể kiểm tra các đối số JVM thực tế khi chạy bằng cách xem cấu hình launch script, container entrypoint hoặc thông tin runtime arguments trong công cụ chẩn đoán. Đừng chỉ kiểm tra file cấu hình trong repository nếu môi trường triển khai còn có thể thêm JVM arguments từ nơi khác.

## 11. Những nhầm lẫn thường gặp

1. **exports đủ cho private reflection:** exports chỉ công khai API theo quy tắc Java; deep reflection cần opens phù hợp.
2. **Mở package cho một module thì mọi module đều truy cập được:** qualified opens chỉ cấp quyền cho target module được chỉ định.
3. **ALL-UNNAMED chỉ là một thư viện:** nó bao gồm tất cả unnamed modules, kể cả module được tạo sau này.
4. **open module là giải pháp tiện lợi cho một lỗi nhỏ:** nó mở toàn bộ package trong module và thường vượt quá nhu cầu.
5. **trySetAccessible chỉ kiểm tra:** khi thành công, nó đã bật cờ override cho đối tượng reflection.
6. **--add-opens sửa được mọi lỗi runtime:** nó không sửa NoSuchMethodError, thiếu class hoặc dependency version mismatch.
7. **Cứ gặp InaccessibleObjectException là mở toàn bộ java.base:** hãy xác định đúng package và caller trước.
8. **Cờ tương thích có thể giữ mãi:** quyền mở runtime cần được theo dõi và loại bỏ khi dependency không còn yêu cầu.

## Kết luận

--add-opens là công cụ để cấp quyền deep reflection qua module boundary, nhưng mỗi lần sử dụng đều làm giảm mức encapsulation của package được mở. Hãy xác định đúng source module, package và target module; ưu tiên qualified opens; hạn chế ALL-UNNAMED và open module; ghi nhận lý do sử dụng cờ runtime và loại bỏ nó khi không còn cần thiết. Cấu hình theo least privilege giúp framework hoạt động mà vẫn giữ phần lớn implementation nội bộ được đóng kín.
