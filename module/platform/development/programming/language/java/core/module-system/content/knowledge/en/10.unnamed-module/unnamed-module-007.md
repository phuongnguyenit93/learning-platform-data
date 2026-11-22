# Giới hạn đóng gói của classpath

Trong Java truyền thống, ứng dụng thường đặt các class và JAR trên **classpath**. Khi chạy theo cách này, các class không thuộc named module được gom vào **unnamed module** của class loader tương ứng. Unnamed module có các quy tắc truy cập rất rộng: nó đọc các module khác, đồng thời các package của nó được xem là đã export và open cho module system.

Điều đó khiến classpath thiếu ranh giới đóng gói ở cấp module. Java vẫn áp dụng các access modifier như `private`, package-private, `protected` và `public`, nhưng không có module descriptor để giới hạn package nào được module khác đọc hoặc mở cho reflection.

## 1. Classpath và unnamed module

Classpath là danh sách thư mục và JAR mà Java dùng để tìm class, resource và một số tài nguyên khác. Ví dụ:

    java -cp "app.jar;libs/*" com.example.app.Main

Trên Windows, dấu phân cách các mục classpath thường là dấu chấm phẩy. Trên Linux và macOS, dấu phân cách là dấu hai chấm.

Khi ứng dụng chạy trên classpath, các class được nạp vào unnamed module của class loader. Unnamed module không có tên module và không có file `module-info.java` để khai báo:

- `requires`: module cần đọc.
- `exports`: package được công bố cho module khác.
- `opens`: package được mở cho deep reflection.
- `uses` và `provides`: quan hệ sử dụng và cung cấp service.

Mỗi class loader có unnamed module riêng. Trong ứng dụng thông thường, các class trên application classpath thuộc unnamed module của application class loader. Vì unnamed module không có tên ổn định, module descriptor không thể viết `requires` tới unnamed module đó.

## 2. Vì sao classpath có ranh giới đóng gói yếu?

Trong unnamed module, các package được export và open theo quy tắc của module system. Vì vậy, một named module có thể đọc các package của unnamed module; đồng thời mã trên classpath có thể đọc các named module đã được resolve theo các quy tắc runtime.

Với classpath, không có danh sách export rõ ràng như:

    module com.example.billing {
        exports com.example.billing.api;
    }

Mọi package trong unnamed module đều được xem là export ở cấp module. Điều này không biến mọi class thành `public`: quy tắc truy cập của ngôn ngữ Java vẫn được áp dụng. Một class package-private vẫn không thể được import và sử dụng tùy ý từ package khác; một field `private` vẫn là private khi truy cập trực tiếp bằng mã Java.

Điểm khác biệt nằm ở **ranh giới module**: classpath không có module descriptor để giới hạn module khác đọc package nào, hoặc package nào được phép deep reflection.

## 3. Access modifier vẫn tồn tại trên classpath

Đóng gói ở cấp ngôn ngữ Java vẫn hoạt động:

| Access modifier | Ý nghĩa cơ bản |
|---|---|
| `private` | Chỉ truy cập trong phạm vi class lồng nhau theo quy tắc Java |
| package-private | Truy cập trong cùng runtime package |
| `protected` | Truy cập trong cùng package hoặc qua quy tắc kế thừa |
| `public` | Truy cập từ nơi có thể đọc và tham chiếu kiểu đó |

Classpath không xóa các quy tắc này. Tuy nhiên, package-private có thể tạo ra một ranh giới yếu hơn nhiều người nghĩ: các class cùng runtime package và cùng class loader có thể truy cập thành viên package-private của nhau, kể cả khi chúng nằm trong các JAR khác nhau.

Ví dụ, hai JAR cùng chứa class thuộc package `com.example.internal`. Nếu chúng được application class loader nạp vào cùng runtime package, các class có thể tương tác qua thành viên package-private. Ranh giới JAR không phải là ranh giới package hoặc module.

Một runtime package được xác định bởi tên package và class loader định nghĩa class. Vì vậy, hai class cùng tên package nhưng được hai class loader khác nhau định nghĩa không nhất thiết thuộc cùng runtime package.

## 4. Reflection trên classpath

Reflection cho phép chương trình xem metadata của class và truy cập thành viên theo các quy tắc runtime. Với class thuộc unnamed module, mọi package được mở cho deep reflection. Vì vậy, chương trình trên classpath thường có thể bật truy cập sâu vào field hoặc method private của class khác bằng `setAccessible(true)` hoặc `trySetAccessible()`, miễn là không vướng các hạn chế khác của Java runtime.

Ví dụ:

    package com.example.domain;

    public final class Account {
        private final String number = "ACC-001";
    }

Một class khác trên classpath có thể dùng reflection:

    package com.example.app;

    import com.example.domain.Account;
    import java.lang.reflect.Field;

    public class Main {
        public static void main(String[] args) throws Exception {
            Account account = new Account();

            Field number = Account.class.getDeclaredField("number");

            if (number.trySetAccessible()) {
                System.out.println(number.get(account));
            }
        }
    }

Với các class thuộc unnamed module, package đã được mở ở cấp module system nên thao tác deep reflection này thường được phép. Điều đó không có nghĩa mã Java bình thường được phép viết `account.number`: truy cập trực tiếp vẫn vi phạm `private`.

Khi class chuyển sang named module, package mặc định không được mở cho module khác. Framework dựa vào reflection có thể bắt đầu gặp `InaccessibleObjectException`. Khi đó cần xem xét `opens` cho đúng package hoặc `open module` nếu thực sự cần mở tất cả package.

## 5. Split package trên classpath

Một hạn chế khác của classpath là nhiều JAR có thể đóng góp class vào cùng package. Ví dụ:

    legacy-a.jar
      com.example.shared.util.MoneyFormatter

    legacy-b.jar
      com.example.shared.util.DateFormatter

Khi cả hai JAR nằm trên classpath, các class có thể được nạp vào cùng unnamed module của class loader. Vì thế, split package vốn có thể tồn tại trong ứng dụng cũ.

Khi chuyển hai JAR thành hai named module riêng trên module path, package `com.example.shared.util` bị chia giữa hai named module. Cấu hình module có thể bị từ chối vì một package không thể có hai chủ sở hữu named module trong cùng module configuration.

Một vấn đề khác là hai JAR có thể chứa cùng một binary class name, chẳng hạn cả hai đều có `com.example.shared.util.Helper`. Với application class loader tiêu chuẩn, thứ tự classpath có thể quyết định bản class nào được tìm thấy trước. Điều này dễ tạo hành vi khó dự đoán khi thứ tự dependency thay đổi.

Do đó, việc ứng dụng chạy được trên classpath không chứng minh rằng cấu trúc package đó đã phù hợp để chuyển sang module path.

## 6. So sánh classpath và named module

| Khía cạnh | Classpath / unnamed module | Named module |
|---|---|---|
| Module descriptor | Không cần `module-info.java` | Có tên module và descriptor |
| Khai báo phụ thuộc | Dựa vào classpath và build tool | Khai báo `requires` |
| Quyền đọc package | Unnamed module đọc các module khác; package của nó được export rộng | Phụ thuộc quan hệ readability |
| Export package | Tất cả package của unnamed module được export ở cấp module | Chỉ package được export mới công khai cho module khác |
| Deep reflection | Các package của unnamed module được mở | Cần `opens` hoặc `open module` cho package cần thiết |
| Split package | Có thể xảy ra giữa các JAR trên classpath | Không được chia giữa các named module trong cùng configuration |
| Service declaration | Thường dùng `META-INF/services` | Có thể dùng `uses` và `provides` trong descriptor |

Named module cho phép tác giả xác định API công khai, phụ thuộc và quyền reflection một cách tường minh. Classpath linh hoạt hơn trong việc ghép JAR nhưng không cung cấp cùng mức kiểm soát ở cấp module.

## 7. Điều gì xảy ra khi trộn classpath và module path?

Một ứng dụng có thể chạy đồng thời với classpath và module path. Các module trên module path được resolve theo module system; class trên classpath thuộc unnamed module của class loader.

Unnamed module đọc mọi named module đã được resolve. Tuy nhiên, một named module không thể khai báo `requires` tới unnamed module vì unnamed module không có tên. Nếu mã trong named module cần một thư viện classpath, đây thường là dấu hiệu cần đưa thư viện đó lên module path, tạo automatic module phù hợp hoặc điều chỉnh kiến trúc.

Khi classpath code truy cập package không được export của một named module, thao tác đó bị module system chặn. Có thể dùng tùy chọn JVM `--add-exports` để cấp quyền truy cập kiểu public cho package cụ thể, hoặc `--add-opens` nếu cần deep reflection. Hai tùy chọn này phục vụ hai mục đích khác nhau.

Ví dụ:

    java --module-path mods
         --add-exports com.example.internal/com.example.internal.api=ALL-UNNAMED
         -cp app.jar com.example.app.Main

Tùy chọn trên cho phép unnamed module truy cập kiểu public trong package được chỉ định của module `com.example.internal`. Nó không tự mở private member cho reflection; trường hợp đó cần `--add-opens`.

## 8. Automatic module không giống unnamed module

Một JAR không có `module-info.class` khi được đặt trên module path có thể trở thành automatic module. Nó vẫn có tên module (được suy ra từ tên JAR hoặc `Automatic-Module-Name`) và tham gia module resolution.

Automatic module khác unnamed module:

- **Unnamed module:** classpath, không có tên module, không thể được tham chiếu bằng `requires`.
- **Automatic module:** JAR trên module path, có tên module và có thể được module khác yêu cầu bằng `requires`.
- Automatic module đọc các module khác và export rộng các package của nó, nhưng vẫn là named module và chịu các quy tắc package uniqueness của module configuration.

Automatic module thường hữu ích như bước chuyển tiếp khi modularize thư viện cũ, nhưng nó không thay thế thiết kế module descriptor tường minh về lâu dài.

## 9. Cách giảm rủi ro khi chuyển classpath sang JPMS

Trước khi chuyển một ứng dụng lớn sang named modules, hãy:

1. Liệt kê các JAR và package mà mỗi JAR chứa.
2. Tìm split package, đặc biệt các package `.internal`, `.common` hoặc `.util` đang được nhiều artifact cùng đóng góp.
3. Xác định package nào là API công khai và package nào chỉ dùng nội bộ.
4. Gom package dùng chung vào một module có trách nhiệm rõ ràng, hoặc tách package theo miền nghiệp vụ.
5. Thêm `module-info.java` với các directive `requires`, `exports`, `opens`, `uses` và `provides` phù hợp.
6. Kiểm tra automatic modules và thư viện chưa modularize.
7. Biên dịch, resolve và chạy ứng dụng trên module path; kiểm tra lại các framework dùng reflection.

Không nên thêm `module-info.java` hàng loạt trước khi kiểm tra package ownership. Làm như vậy có thể biến các dependency vốn chạy trên classpath thành một module graph không hợp lệ.

## 10. Những nhầm lẫn thường gặp

- **Tưởng package uniqueness có nghĩa toàn bộ ứng dụng chỉ được có một package name.** Quy tắc áp dụng cho các named module trong cùng module configuration; unnamed module và các class loader có quy tắc riêng.
- **Tưởng hai module không có class trùng tên thì không thể split package.** Chỉ cần cùng khai báo một package, dù class khác tên, vẫn có thể xung đột.
- **Tưởng package con trùng với package cha.** `com.example.api` và `com.example.api.internal` là hai package riêng.
- **Tưởng exports tạo quyền sở hữu package.** Module sở hữu package dựa trên nội dung module; exports chỉ điều khiển khả năng truy cập.
- **Tưởng classpath và module path có cùng quy tắc đóng gói.** Classpath gom class vào unnamed module; named module có descriptor và package ownership chặt chẽ hơn.
- **Tưởng automatic module là unnamed module.** Automatic module có tên và được resolve như một named module.
- **Tưởng thêm `--add-exports` sẽ sửa split package.** Tùy chọn này điều chỉnh quyền truy cập, không hợp nhất package hoặc thay đổi module sở hữu.

## Ghi nhớ

Classpath gom các JAR vào unnamed module nên nhiều artifact có thể cùng đóng góp class vào một package. Khi chuyển sang named modules, package phải có chủ sở hữu rõ ràng trong module configuration; split package giữa các named module sẽ gây xung đột.

Nếu nhiều module cần dùng chung một package, hãy đưa package đó về một module shared. Nếu các class thuộc trách nhiệm riêng, hãy tách package theo module. Kiểm tra package ownership là một bước quan trọng trước khi chuyển một hệ thống cũ từ classpath sang module path.