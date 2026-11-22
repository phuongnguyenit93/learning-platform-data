# requires static cho phụ thuộc cần lúc biên dịch

## 1. Mục đích của requires static

Trong Java Platform Module System (JPMS), directive **requires** khai báo một module phụ thuộc mà module hiện tại cần đọc. Mặc định, phụ thuộc đó phải được tìm thấy khi biên dịch và khi tạo cấu hình module lúc chạy.

Directive **requires static** biểu thị một phụ thuộc có hai yêu cầu khác nhau theo từng giai đoạn:

- **Khi biên dịch:** module được khai báo vẫn bắt buộc phải có mặt trên module path để javac phân giải kiểu và kiểm tra mã nguồn.
- **Khi chạy:** module đó là tùy chọn. JVM có thể khởi động module hiện tại dù module phụ thuộc không có mặt trên module path.

Cú pháp này phù hợp khi mã nguồn cần biết một kiểu ở thời điểm biên dịch nhưng ứng dụng không cần kiểu đó để thực hiện luồng chạy thông thường. Ví dụ phổ biến là thư viện annotation có retention ở mức CLASS, hoặc một integration tùy chọn mà ứng dụng chỉ dùng khi thành phần đó được cài đặt.

**requires static** là một phần của JPMS từ Java 9 và vẫn được hỗ trợ trong các JDK hiện hành.

## 2. Cú pháp và vị trí khai báo

Directive được đặt trong thân file module-info.java:

~~~java
module com.example.application {
    requires static com.example.annotations;
}
~~~

Trong đó:

- **requires** khai báo một quan hệ phụ thuộc giữa các module.
- **static** đánh dấu phụ thuộc là bắt buộc ở thời điểm biên dịch nhưng tùy chọn ở thời điểm chạy.
- **com.example.annotations** là tên module cần phụ thuộc.

Có thể kết hợp với **transitive**:

~~~java
module com.example.api {
    requires static transitive com.example.annotations;
}
~~~

Kết hợp này giữ hai ý nghĩa:

1. Module hiện tại cần module được chỉ định khi biên dịch.
2. Module đọc module hiện tại cũng được hưởng quan hệ readability bắc cầu đối với module được chỉ định khi module đó được phân giải.

Các modifier của requires có thể kết hợp theo cú pháp của module declaration. Mỗi module chỉ khai báo một directive requires cho một module đích; nếu cần nhiều thuộc tính, kết hợp modifier trong cùng directive.

Mọi named module thông thường đều có phụ thuộc ngầm định vào **java.base**. Không cần khai báo requires static java.base.

## 3. So sánh requires và requires static

| Directive | Bắt buộc khi biên dịch | Bắt buộc khi chạy | Ý nghĩa chính |
|---|---|---|---|
| requires M | Có | Có | Phụ thuộc cần thiết ở cả hai giai đoạn |
| requires static M | Có | Không | Phụ thuộc cần để biên dịch, có thể vắng mặt khi chạy |
| requires transitive M | Có | Có | Phụ thuộc bắt buộc và được truyền readability cho module đọc module hiện tại |
| requires static transitive M | Có | Không | Phụ thuộc cần khi biên dịch, tùy chọn khi chạy và có tính bắc cầu |

**Readability** là quyền một module đọc các kiểu được module khác export. Nó không đồng nghĩa với quyền truy cập mọi package hoặc mọi thành viên; quyền truy cập vẫn tuân theo exports, opens và các quy tắc truy cập của Java.

Một điểm quan trọng: requires static không làm cho kiểu của module phụ thuộc tự biến mất khỏi bytecode. Nếu chương trình thực sự tải hoặc gọi một lớp thuộc module tùy chọn trong lúc module đó vắng mặt, thao tác đó vẫn có thể thất bại với lỗi liên kết hoặc lỗi nạp lớp. Tính tùy chọn chỉ có nghĩa là JPMS không bắt buộc module đó phải hiện diện để phân giải module hiện tại.

## 4. Vòng đời của phụ thuộc static

### 4.1. Khi biên dịch

Giả sử module ứng dụng khai báo:

~~~java
module com.example.application {
    requires static com.example.annotations;
}
~~~

Khi biên dịch, javac phải tìm được module com.example.annotations trên module path hoặc trong module source path. Nếu không tìm thấy, compiler không thể phân giải module và sẽ báo lỗi.

Lý do là mã nguồn ứng dụng có thể import và sử dụng kiểu do module phụ thuộc cung cấp. Compiler cần biết định nghĩa kiểu đó để kiểm tra tên, kiểu dữ liệu, annotation và chữ ký phương thức.

### 4.2. Khi chạy

Khi tạo cấu hình module, JVM không bắt buộc phải tìm thấy module được yêu cầu bằng requires static.

Có hai tình huống:

- **Module có mặt trên module path:** module đó có thể được phân giải và sử dụng theo quan hệ module đã khai báo.
- **Module vắng mặt:** module hiện tại vẫn có thể được phân giải nếu các phụ thuộc bắt buộc khác đều hợp lệ. Mã chạy không được thực hiện thao tác cần nạp lớp từ module đã vắng mặt.

Ví dụ, một annotation có retention CLASS được ghi vào file class nhưng không được cung cấp qua Core Reflection API ở runtime. Ứng dụng có thể biên dịch với module annotation, sau đó chạy mà không cần đóng gói module annotation nếu chương trình không cần đọc annotation đó bằng reflection.

### 4.3. Khi mã chạy thật sự cần module tùy chọn

requires static không tự động thay thế implementation, không tạo lớp dự phòng và không xử lý lỗi thiếu dependency. Nếu chương trình gọi một lớp thuộc module đang vắng mặt, JVM có thể ném NoClassDefFoundError hoặc một lỗi liên kết tương ứng.

Vì vậy, mã sử dụng phụ thuộc tùy chọn cần được thiết kế để chỉ tải hoặc gọi lớp đó khi module đã được cung cấp. Có thể tách phần tích hợp tùy chọn thành module riêng, hoặc kiểm tra cấu hình triển khai trước khi kích hoạt tính năng.

## 5. Ví dụ hoàn chỉnh: annotation chỉ cần khi biên dịch

Ví dụ gồm hai module:

- **com.example.trace** cung cấp annotation BuildTrace.
- **com.example.app** sử dụng annotation này và khai báo requires static.

Annotation được đặt retention là CLASS. Nó được lưu trong file class nhưng không cần được nạp để chạy chương trình thông thường.

### 5.1. Cấu trúc thư mục

~~~text
src/
├── com.example.trace/
│   ├── module-info.java
│   └── com/example/trace/BuildTrace.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

### 5.2. Module annotation

File src/com.example.trace/module-info.java:

~~~java
module com.example.trace {
    exports com.example.trace;
}
~~~

File src/com.example.trace/com/example/trace/BuildTrace.java:

~~~java
package com.example.trace;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
public @interface BuildTrace {
    String value();
}
~~~

Annotation này được compiler ghi vào metadata của class. Vì retention là CLASS, annotation không được trả về qua các API reflection thông thường tại runtime.

### 5.3. Module ứng dụng

File src/com.example.app/module-info.java:

~~~java
module com.example.app {
    requires static com.example.trace;
}
~~~

File src/com.example.app/com/example/app/Main.java:

~~~java
package com.example.app;

import com.example.trace.BuildTrace;

@BuildTrace("compiled with optional metadata")
public final class Main {
    public static void main(String[] args) {
        System.out.println("Application runs without optional module.");
    }
}
~~~

Ở đây, ứng dụng cần BuildTrace để biên dịch nên module com.example.trace phải có mặt trong giai đoạn javac. Khi chạy, annotation CLASS không cần được nạp để thực thi main.

### 5.4. Biên dịch cả hai module

Chạy lệnh tại thư mục chứa src:

~~~bash
javac --module-source-path src -d out -m com.example.trace,com.example.app
~~~

Sau lệnh này, thư mục out có cấu trúc:

~~~text
out/
├── com.example.trace/
│   ├── module-info.class
│   └── com/example/trace/BuildTrace.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

Module annotation có mặt trong out để javac phân giải kiểu BuildTrace. File module-info.class của ứng dụng ghi nhận quan hệ requires static.

### 5.5. Chạy khi module annotation có mặt

~~~bash
java --module-path out -m com.example.app/com.example.app.Main
~~~

Kết quả:

~~~text
Application runs without optional module.
~~~

### 5.6. Chạy khi module annotation vắng mặt

Để kiểm chứng phụ thuộc thực sự tùy chọn ở runtime, tạo module path mới chỉ chứa output của ứng dụng.

Trên Linux hoặc macOS:

~~~bash
mkdir runtime
cp -R out/com.example.app runtime/
java --module-path runtime -m com.example.app/com.example.app.Main
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory runtime
Copy-Item -Recurse out/com.example.app runtime/
java --module-path runtime -m com.example.app/com.example.app.Main
~~~

Kết quả vẫn là:

~~~text
Application runs without optional module.
~~~

Module com.example.trace không có trong runtime nhưng JVM vẫn phân giải và chạy com.example.app. Đây là hành vi mà requires static cung cấp.

Ví dụ đã được biên dịch và chạy thử với JDK 24.0.2 ở cả hai trường hợp: module annotation có mặt và module annotation vắng mặt.

## 6. Khi nào nên dùng requires static?

Nên cân nhắc directive này trong các trường hợp sau:

- **Annotation chỉ phục vụ biên dịch:** mã nguồn dùng annotation để compiler hoặc công cụ build đọc metadata, nhưng ứng dụng không cần annotation ở runtime. Ví dụ cần retention CLASS.
- **Tích hợp tùy chọn:** module có thể biên dịch với API của một integration, nhưng luồng chạy cơ bản không yêu cầu integration đó.
- **API có phụ thuộc tùy chọn:** module công khai một API có kiểu liên quan đến module khác và muốn truyền readability ở thời điểm biên dịch bằng requires static transitive. Cần thiết kế rõ điều kiện runtime để người dùng API không vô tình gọi kiểu vắng mặt.

Không nên dùng requires static cho module mà ứng dụng luôn cần để khởi động hoặc xử lý nghiệp vụ chính. Trường hợp đó nên dùng requires thông thường để hệ thống phát hiện thiếu dependency ngay khi phân giải module.

## 7. requires static transitive trong API

Giả sử module com.example.api công khai một API có sử dụng kiểu từ module com.example.annotations. Nếu các module tiêu thụ API cần đọc kiểu annotation đó trong lúc biên dịch, có thể khai báo:

~~~java
module com.example.api {
    requires static transitive com.example.annotations;
    exports com.example.api;
}
~~~

Ý nghĩa:

- com.example.api bắt buộc cần com.example.annotations khi biên dịch.
- Module đọc com.example.api được truyền quan hệ readability tới com.example.annotations.
- Ở runtime, com.example.annotations vẫn là phụ thuộc tùy chọn.

Không nên thêm transitive chỉ để làm cho tất cả module downstream nhìn thấy dependency. Modifier này ảnh hưởng tới module graph của các module tiêu thụ API và nên được dùng khi đó thực sự là một phần của hợp đồng API.

Nếu kiểu từ module tùy chọn xuất hiện trong chữ ký public, người dùng API cần hiểu rằng họ vẫn phải cung cấp module đó khi thực thi những thao tác cần kiểu này. Readability ở thời điểm biên dịch không bảo đảm lớp có mặt ở runtime.

## 8. Phân biệt với cấu hình dependency của Maven và Gradle

requires static là directive của JPMS. Nó điều khiển quan hệ module và yêu cầu phân giải module ở compile time/runtime.

Nó không tự quyết định thư viện có được đóng gói vào ứng dụng hay không. Việc tải, đóng gói hoặc loại dependency vẫn do công cụ build và cấu hình triển khai quyết định.

Một số cấu hình như compileOnly trong Gradle hoặc dependency scope tương ứng trong công cụ build có mục tiêu gần giống về mặt vòng đời dependency, nhưng chúng không thay thế module-info.java. Cần cấu hình cả module graph và dependency của build khi dự án sử dụng JPMS.

Ví dụ: nếu module annotation cần cho javac nhưng không cần ở runtime, dự án phải bảo đảm compiler nhìn thấy annotation module trong lúc biên dịch. Đồng thời, gói runtime có thể loại module đó khi ứng dụng không cần nó. Chỉ viết requires static không tự động loại JAR khỏi thư mục phân phối.

## 9. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| javac báo không tìm thấy module | Module phụ thuộc không có trên module path khi biên dịch | Bổ sung module vào module path hoặc module source path |
| Biên dịch được nhưng chạy báo NoClassDefFoundError | Mã đã thực sự tải hoặc gọi kiểu thuộc module tùy chọn đang vắng mặt | Chỉ kích hoạt phần mã cần dependency khi dependency có mặt; hoặc chuyển sang requires thông thường nếu dependency là bắt buộc |
| Ứng dụng chạy được nhưng reflection không tìm thấy annotation | Annotation dùng RetentionPolicy.CLASS nên không có trong dữ liệu annotation runtime | Nếu cần đọc annotation bằng reflection, dùng RetentionPolicy.RUNTIME và cung cấp module annotation ở runtime |
| Dùng requires static cho thư viện cốt lõi | Phụ thuộc thực tế luôn cần khi chạy | Dùng requires để JVM phát hiện thiếu module khi phân giải |
| Nhầm requires static với compileOnly | Cho rằng directive JPMS tự loại JAR khỏi gói triển khai | Cấu hình riêng dependency scope và packaging của công cụ build |
| Khai báo transitive không cần thiết | Truyền readability cho mọi module tiêu thụ dù API không cần | Chỉ dùng transitive khi phụ thuộc là một phần của hợp đồng API |
| Thiếu module khi chạy tính năng tùy chọn | Tính năng gọi trực tiếp lớp từ module không có mặt | Tách integration thành module riêng hoặc kiểm tra cấu hình trước khi tải lớp |

Lưu ý riêng về annotation: RetentionPolicy.CLASS không làm annotation biến mất khỏi file class; nó chỉ không cung cấp annotation đó qua reflection ở runtime. Nếu công cụ hoặc framework cần đọc annotation sau khi ứng dụng chạy, module annotation và annotation type phải có mặt khi thực hiện thao tác đó.

## 10. Kiểm tra module descriptor

Sau khi biên dịch, có thể dùng công cụ JDK để kiểm tra khai báo requires static trong module-info.class.

Xem thông tin module trong output:

~~~bash
jar --describe-module --file out/com.example.app/module-info.class
~~~

Để xem cấu trúc class file chi tiết:

~~~bash
javap -v out/com.example.app/module-info.class
~~~

Trong kết quả javap, phần Module attribute có thể hiển thị cờ **ACC_STATIC_PHASE** trên dependency com.example.trace. Đây là cách biểu diễn nhị phân của modifier static trong requires. Nếu kết hợp transitive, cờ **ACC_TRANSITIVE** cũng được ghi nhận.

Khi kiểm tra, cần xác nhận:

- Tên module đích đúng với tên được khai báo trong module-info.java.
- Dependency có cờ static phase.
- Dependency không bị khai báo nhầm thành requires thông thường.
- Cấu hình chạy không chứa module tùy chọn nếu muốn kiểm tra trường hợp vắng mặt.

## 11. Checklist sử dụng

- Xác định dependency thực sự chỉ bắt buộc khi biên dịch.
- Đưa module phụ thuộc lên module path khi chạy javac.
- Khai báo requires static trong module-info.java.
- Không dùng requires static cho dependency cốt lõi cần ở runtime.
- Kiểm tra code path để bảo đảm không tải kiểu tùy chọn khi module vắng mặt.
- Nếu dùng annotation, chọn retention phù hợp với nhu cầu compile time hay reflection runtime.
- Chỉ thêm transitive khi phụ thuộc thuộc hợp đồng API.
- Cấu hình packaging riêng trong Maven, Gradle hoặc công cụ build đang sử dụng.
- Kiểm thử cả hai trường hợp: dependency có mặt và dependency vắng mặt ở runtime.
- Dùng javap hoặc jar để kiểm tra descriptor nhị phân sau khi biên dịch.

## Tài liệu tham khảo

- [Java Language Specification — Module Declarations](https://docs.oracle.com/javase/specs/jls/se27/html/jls-7.html) — cú pháp module declaration và requires directive.
- [Java Virtual Machine Specification — The Module Attribute](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-4.html) — cách biểu diễn các modifier của requires trong module-info.class.
