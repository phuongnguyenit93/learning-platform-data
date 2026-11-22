# Vì sao classpath cần một mô hình module rõ ràng hơn

Trong những chương trình Java nhỏ, classpath thường đủ để đưa các thư mục và JAR cần thiết vào lúc biên dịch và chạy ứng dụng. Khi dự án lớn dần, nhiều thư viện và nhóm phát triển cùng tham gia, classpath bộc lộ một hạn chế quan trọng: nó cho JVM biết **tìm lớp ở đâu**, nhưng không mô tả rõ **thành phần nào phụ thuộc vào thành phần nào** và **phần nào được phép sử dụng**.

Java Platform Module System (JPMS), được đưa vào từ Java 9, bổ sung một mô hình để khai báo ranh giới và quan hệ phụ thuộc giữa các module. Mô hình này giúp cấu trúc ứng dụng dễ đọc, dễ kiểm soát và dễ bảo trì hơn.

## 1. Classpath giải quyết việc gì?

Classpath là danh sách các thư mục và tệp JAR mà trình nạp lớp có thể tìm kiếm khi ứng dụng cần một lớp hoặc tài nguyên. Khi chạy chương trình, ta thường truyền classpath bằng tùy chọn `-cp` hoặc `-classpath`.

Ví dụ:

```shell
java -cp "app.jar;lib/*" com.example.Main
```

Trên Windows, dấu phân cách các mục classpath thường là dấu chấm phẩy; trên Linux và macOS là dấu hai chấm. Ví dụ trên minh họa ý tưởng: ứng dụng và các thư viện được đặt vào cùng một danh sách tìm kiếm.

Classpath rất thực dụng. Ta có thể thêm JAR, thay một thư viện hoặc chạy ứng dụng mà không cần khai báo một cấu trúc module mới. Các công cụ như Maven và Gradle cũng có thể giải quyết dependency rồi tạo classpath phù hợp cho tác vụ biên dịch hoặc chạy.

Vấn đề xuất hiện khi danh sách này trở thành cách duy nhất để mô tả cấu trúc của một hệ thống lớn. Ở thời điểm chạy, classpath chủ yếu là một danh sách đã được làm phẳng. JVM không nhận được một bản mô tả đầy đủ về ý định kiến trúc của từng thư viện.

## 2. Những giới hạn của một classpath phẳng

### 2.1. Quan hệ phụ thuộc không được khai báo tại ranh giới thành phần

Giả sử ứng dụng có ba phần:

- `catalog` quản lý danh mục sản phẩm.
- `orders` tạo và xử lý đơn hàng.
- `reports` tổng hợp dữ liệu để lập báo cáo.

Về mặt kiến trúc, `orders` có thể cần dùng API của `catalog`, còn `reports` có thể cần đọc dữ liệu từ cả hai. Nhưng khi tất cả JAR nằm trên cùng classpath, các lớp có thể nhìn thấy nhau rộng hơn mức kiến trúc mong muốn.

Nếu `orders` vô tình gọi một lớp triển khai nội bộ của `catalog`, classpath không có quy tắc module để ngăn việc đó. Lời gọi có thể biên dịch và chạy được, dù nó tạo ra một phụ thuộc không nên tồn tại.

Điều này khiến ranh giới kiến trúc phụ thuộc nhiều vào quy ước của nhóm và cách tổ chức mã nguồn. Khi người khác thay đổi cấu trúc bên trong một thư viện, những nơi đã sử dụng lớp nội bộ có thể bị ảnh hưởng.

### 2.2. Khó phân biệt API công khai với phần triển khai nội bộ

Java đã có phạm vi truy cập `public`, `protected`, package-private và `private`. Tuy nhiên, các mức này chưa tạo ra một ranh giới ở cấp module.

Một lớp `public` trong JAR thường có thể được mã nguồn khác trên classpath sử dụng nếu lớp đó được tìm thấy và các điều kiện truy cập thông thường được đáp ứng. Vì vậy, thư viện khó diễn đạt rằng:

- Những package nào là API được hỗ trợ.
- Những package nào chỉ phục vụ triển khai nội bộ.
- Thành phần nào được phép truy cập sâu bằng reflection.

Trong hệ thống lớn, sự khác biệt này rất quan trọng. Nếu người dùng thư viện phụ thuộc vào lớp nội bộ, nhóm phát triển thư viện sẽ khó thay đổi cách triển khai mà không gây ảnh hưởng ngược.

### 2.3. Lớp trùng tên và thứ tự tìm kiếm có thể gây bất ngờ

Classpath có thứ tự. Nếu nhiều mục chứa cùng một tên lớp đầy đủ, trình nạp lớp có thể tìm thấy một bản trước các bản còn lại theo thứ tự tìm kiếm của nó. Ứng dụng khi đó có thể chạy với phiên bản lớp khác với điều mà người phát triển dự kiến.

Tình huống này thường xuất hiện khi:

- Hai thư viện đóng gói các lớp có cùng tên đầy đủ.
- Một JAR cũ vẫn còn trong classpath sau khi đã nâng cấp thư viện.
- Một ứng dụng có nhiều bản phụ thuộc gián tiếp.
- Các package bị chia sẻ giữa nhiều JAR mà không có quy ước sở hữu rõ ràng.

Vấn đề không chỉ nằm ở tên lớp. Việc tìm tài nguyên cũng có thể chịu ảnh hưởng của thứ tự classpath. Kết quả là một lỗi cấu hình đôi khi trông giống lỗi logic trong chương trình.

### 2.4. Classpath không thể hiện dependency graph ở thời điểm chạy

Maven hoặc Gradle có thể biết dependency trực tiếp, dependency bắc cầu và phiên bản được chọn. Nhưng sau khi công cụ build tạo classpath, thông tin đó phần lớn đã trở thành một danh sách đường dẫn.

Từ danh sách này, JVM không thể dễ dàng biết:

- JAR nào là dependency trực tiếp của thành phần nào.
- Thành phần nào thực sự cần một thư viện.
- Package nào nên được cung cấp cho module khác.
- Một dependency đang bị sử dụng ngoài ý định kiến trúc hay không.

Nói cách khác, công cụ build có thể hiểu đồ thị dependency, trong khi classpath runtime chỉ thể hiện tập hợp các vị trí tìm kiếm. Hai khái niệm này có liên quan nhưng không giống nhau.

### 2.5. Khó kiểm soát sự thay đổi trong hệ thống lớn

Khi ranh giới thành phần không được thực thi, một thay đổi nhỏ có thể lan sang nhiều phần khác. Một lớp nội bộ trở thành điểm phụ thuộc không chính thức; một dependency cũ vẫn tồn tại vì không ai chắc nơi nào đang sử dụng nó; hoặc hai nhóm vô tình tạo ra các package có tên giống nhau.

Những vấn đề này làm tăng chi phí đọc hiểu, refactor và nâng cấp. Chúng cũng khiến việc xác định trách nhiệm của từng thư viện khó khăn hơn.

## 3. Mô hình module bổ sung điều gì?

JPMS đưa khái niệm **module có tên** vào nền tảng Java. Một module là một nhóm package và tài nguyên có danh tính riêng, kèm theo mô tả về dependency và những package được công khai.

Mô tả này thường được viết trong tệp `module-info.java` ở gốc source set của module. Khi biên dịch, tệp này trở thành `module-info.class` trong artifact.

Một module có thể khai báo:

- `requires`: module mà nó cần đọc và sử dụng.
- `exports`: package được công khai cho module khác.
- `opens`: package được mở cho reflection sâu trong các trường hợp cần thiết.
- `uses` và `provides`: quan hệ sử dụng và cung cấp dịch vụ theo cơ chế ServiceLoader.
- `requires transitive`: dependency mà các module phụ thuộc vào module hiện tại cũng cần có khả năng đọc.

Ví dụ, module danh mục có thể công khai API và giữ phần triển khai bên trong:

```java
module com.example.catalog {
    exports com.example.catalog.api;
}
```

Module đơn hàng khai báo rõ dependency của mình:

```java
module com.example.orders {
    requires com.example.catalog;
    requires java.sql;

    exports com.example.orders.api;
}
```

Từ mô tả này, người đọc biết rằng `orders` phụ thuộc vào `catalog` và `java.sql`. Module khác có thể sử dụng các kiểu public thuộc package `com.example.orders.api`, nhưng không tự động được truy cập package triển khai chưa được export.

### 3.1. Readability: module nào được phép đọc module nào?

Một module không tự động nhìn thấy mọi module khác trên module path. Nó phải khai báo dependency bằng `requires`.

Khai báo này tạo nên đồ thị module. Khi khởi động, hệ thống phân giải đồ thị để xác định các module cần thiết và quan hệ đọc giữa chúng. Nếu một dependency bắt buộc không thể được phân giải, ứng dụng có thể thất bại ngay ở bước khởi động thay vì chỉ phát hiện lỗi khi một nhánh chức năng được gọi.

`requires transitive` hữu ích khi API của module A để lộ kiểu dữ liệu thuộc module B. Nếu module C phụ thuộc vào A, khai báo bắc cầu giúp C đọc được B thông qua quan hệ đã được A công bố.

### 3.2. Exports: module nào được phép sử dụng package nào?

`exports` công khai một package cho các module khác. Đây là ranh giới API ở cấp module.

Ví dụ, `com.example.catalog.api` có thể chứa các kiểu mà người dùng thư viện cần, còn `com.example.catalog.internal` giữ thuật toán, adapter hoặc chi tiết lưu trữ. Khi package nội bộ không được export, module khác không thể sử dụng các kiểu public trong package đó như một API thông thường.

Cách tổ chức này tạo ra một hợp đồng rõ hơn: người dùng module dựa vào phần được công khai, còn nhóm phát triển có không gian thay đổi phần nội bộ.

### 3.3. Opens: hỗ trợ reflection mà vẫn giữ ranh giới

Một số framework cần reflection sâu để đọc hoặc thay đổi thành viên không public, chẳng hạn khi ánh xạ object, inject dependency hoặc tuần tự hóa dữ liệu.

`opens` cho phép mở package cho mục đích reflection sâu. Phạm vi mở có thể rộng hoặc giới hạn cho một module cụ thể. Điều này khác với `exports`: export công khai API Java thông thường, còn open cho phép reflection sâu trong phạm vi được khai báo.

Vì vậy, khi chuyển một ứng dụng sang JPMS, các framework cần reflection có thể cần cấu hình `opens` phù hợp. Không nên mở toàn bộ module một cách tùy tiện vì như vậy sẽ làm giảm lợi ích của ranh giới module.

## 4. Classpath và module path khác nhau như thế nào?

Classpath và module path đều đưa thư viện vào quá trình chạy, nhưng chúng thể hiện hai mô hình khác nhau.

| Khía cạnh | Classpath | Module path |
|---|---|---|
| Mô hình | Danh sách thư mục/JAR để tìm lớp | Tập hợp module có danh tính và quan hệ rõ ràng |
| Mô tả dependency | Không có trong classpath runtime đã làm phẳng | Khai báo bằng `requires` |
| Phạm vi package | Không có danh sách export ở cấp module | Khai báo bằng `exports` |
| Encapsulation | Chủ yếu dựa vào quy tắc truy cập Java và classloader | Có thêm ranh giới module, export và open |
| Dependency cũ | JAR đặt trên classpath hoạt động theo mô hình classpath | JAR không có descriptor có thể trở thành automatic module khi đặt trên module path |
| Kiểm tra cấu trúc | Nhiều vấn đề chỉ xuất hiện khi lớp được nạp hoặc chức năng được gọi | Module graph được phân giải khi khởi động |

Các lớp được nạp từ classpath thuộc unnamed module gắn với classloader tương ứng. Unnamed module có khả năng đọc các module khác, nhưng module có tên không thể khai báo `requires` trực tiếp tới unnamed module. Vì vậy, khi thiết kế module có tên, dependency của nó cần được cung cấp dưới dạng module có thể phân giải.

Một JAR chưa có `module-info.class` vẫn có thể được đặt trên module path dưới dạng **automatic module**. Tên module có thể lấy từ thuộc tính `Automatic-Module-Name` trong manifest; nếu không có, tên được suy ra từ tên tệp JAR. Automatic module giúp thư viện cũ tham gia quá trình chuyển đổi, nhưng không cung cấp ranh giới package chi tiết như một module có descriptor được thiết kế rõ ràng.

## 5. Ví dụ về ranh giới API trong một ứng dụng

Giả sử một ứng dụng bán hàng có cấu trúc như sau:

```text
catalog/
└── src/main/java/
    ├── module-info.java
    └── com/example/catalog/
        ├── api/
        │   └── Product.java
        └── internal/
            └── ProductRepositoryImpl.java

orders/
└── src/main/java/
    ├── module-info.java
    └── com/example/orders/
        ├── api/
        │   └── OrderService.java
        └── internal/
            └── OrderServiceImpl.java
```

Module `catalog` chỉ export package API:

```java
module com.example.catalog {
    exports com.example.catalog.api;
}
```

Module `orders` yêu cầu `catalog`:

```java
module com.example.orders {
    requires com.example.catalog;
    exports com.example.orders.api;
}
```

Khi đó, `orders` có thể sử dụng `Product` từ API của `catalog`. Nó không thể dựa vào `ProductRepositoryImpl` trong package nội bộ của `catalog` như một API thông thường.

Nếu sau này nhóm phát triển thay đổi cách lưu sản phẩm, họ có thể thay thế `ProductRepositoryImpl` mà không cần giữ tương thích với những module đã tuân thủ ranh giới công khai. Module system giúp biến quy ước kiến trúc thành quy tắc mà công cụ biên dịch và runtime có thể thực thi.

## 6. JPMS có thay thế Maven hoặc Gradle không?

Không. Cần phân biệt **module của hệ thống build** với **module của JPMS**.

Maven và Gradle quản lý project, dependency artifact, phiên bản thư viện, plugin, tác vụ build và đóng gói. JPMS mô tả module ở cấp nền tảng Java: module nào tồn tại, module nào đọc module nào và package nào được công khai.

Một dự án Gradle có thể có nhiều subproject nhưng không phải subproject nào cũng cần một JPMS module riêng. Ngược lại, một project build có thể đóng gói hoặc biên dịch các module JPMS theo cấu trúc mà dự án lựa chọn.

JPMS cũng không thay thế bộ quản lý dependency. Nó không giải quyết đầy đủ việc chọn phiên bản thư viện, tải artifact từ repository hay quản lý dependency bắc cầu. Những việc đó vẫn thuộc công cụ build. Module system bổ sung cấu trúc và quy tắc truy cập cho các module đã được cung cấp.

## 7. Mô hình module không giải quyết mọi vấn đề

JPMS làm rõ ranh giới và dependency ở cấp module, nhưng không phải một cơ chế sandbox bảo mật cho mã Java. Các module vẫn chạy trong cùng tiến trình và chia sẻ quyền của tiến trình đó. Nếu ứng dụng cần cô lập mã không tin cậy, cần một kiến trúc cách ly phù hợp khác.

Module system cũng không tự động sửa thiết kế package, loại bỏ dependency vòng hoặc chọn phiên bản thư viện tương thích. Nếu module được thiết kế quá lớn, export quá rộng hoặc mở mọi package cho reflection, lợi ích về encapsulation sẽ giảm đáng kể.

Do đó, JPMS nên được xem là một công cụ để biểu đạt và thực thi ranh giới kiến trúc. Nó phát huy hiệu quả khi nhóm xác định được API công khai, dependency hợp lệ và phần triển khai cần giữ kín.

## 8. Chuyển đổi từ classpath sang module path

Không nhất thiết phải chuyển toàn bộ ứng dụng trong một lần. Một lộ trình từng bước thường dễ kiểm soát hơn:

1. **Kiểm kê dependency:** xác định JAR trực tiếp, dependency bắc cầu, các package trùng và những API nội bộ của JDK đang được sử dụng.
2. **Ổn định tên module:** với thư viện chưa có descriptor, có thể khai báo `Automatic-Module-Name` trong manifest để tên module không phụ thuộc vào cách đặt tên tệp JAR.
3. **Làm rõ package:** xử lý package bị chia sẻ giữa nhiều thư viện và xác định package nào là API, package nào là triển khai nội bộ.
4. **Thêm descriptor:** tạo `module-info.java`, khai báo các dependency thật sự cần thiết bằng `requires`, chỉ export package cần công khai.
5. **Cấu hình framework:** mở đúng package bằng `opens` khi framework cần reflection sâu.
6. **Kiểm tra dependency JDK:** có thể dùng `jdeps --jdk-internals` để tìm việc sử dụng API nội bộ của JDK và lên kế hoạch thay thế.
7. **Dùng tùy chọn chuyển tiếp khi cần:** `--add-reads`, `--add-exports` và `--add-opens` có thể giúp ứng dụng chuyển đổi dần, nhưng nên được xem là biện pháp chuyển tiếp có phạm vi rõ ràng.

Classpath vẫn được Java hỗ trợ. Một ứng dụng nhỏ, công cụ nội bộ hoặc hệ thống cũ có thể tiếp tục dùng classpath nếu mô hình hiện tại phù hợp. Giá trị của JPMS rõ hơn khi dự án cần ranh giới API ổn định, nhiều thành phần phối hợp và khả năng kiểm soát dependency ở cấp module.

## 9. Khi nào nên quan tâm đến mô hình module?

Mô hình module đặc biệt hữu ích khi:

- Ứng dụng có nhiều thư viện hoặc nhiều nhóm cùng phát triển.
- Các package nội bộ thường bị sử dụng từ bên ngoài.
- Dependency giữa các thành phần khó theo dõi.
- Việc nâng cấp một thư viện thường gây lỗi ở những thành phần không liên quan.
- Nhóm muốn công khai một API ổn định và giữ quyền thay đổi phần triển khai.
- Ứng dụng cần kiểm soát rõ những package được mở cho reflection.

Với một chương trình nhỏ chỉ có vài JAR và ít ranh giới kiến trúc, classpath có thể vẫn là lựa chọn đơn giản, hợp lý. Không cần thêm module descriptor chỉ vì dự án sử dụng Java hiện đại. Nên chọn JPMS khi các ranh giới đó mang lại giá trị thực tế cho cách tổ chức và bảo trì hệ thống.

## Kết luận

Classpath giúp Java tìm lớp từ các thư mục và JAR, nhưng không thể hiện đầy đủ cấu trúc dependency và quyền truy cập giữa các thành phần. Khi hệ thống lớn lên, danh sách classpath phẳng khiến API công khai, phần triển khai nội bộ và quan hệ phụ thuộc dễ bị lẫn lộn.

JPMS bổ sung module có tên, dependency tường minh, export package và cơ chế mở package cho reflection. Nhờ đó, kiến trúc được mô tả ngay trong mã nguồn và có thể được kiểm tra trong quá trình biên dịch, phân giải module và chạy ứng dụng.

Điểm cốt lõi là: classpath trả lời câu hỏi “JVM tìm lớp ở đâu?”, còn mô hình module còn trả lời “thành phần nào cần thành phần nào, và phần nào được phép sử dụng?”.