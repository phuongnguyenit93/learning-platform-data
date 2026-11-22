# Đồ thị phụ thuộc tại lúc biên dịch, liên kết và chạy

## Mục tiêu

Trong Java Platform Module System (JPMS), một ứng dụng được chia thành các module có tên và có mô tả phụ thuộc rõ ràng. Đồ thị phụ thuộc cho biết module nào cần đọc module nào để sử dụng API của module đó. Đồ thị được phân giải ở thời điểm biên dịch và chạy; nếu cần đóng gói một runtime riêng, công cụ jlink cũng phân giải đồ thị để chọn những module cần đưa vào ảnh runtime.

Sau bài này, bạn có thể:

- Đọc quan hệ phụ thuộc từ module-info.java và diễn giải chiều của cạnh trong đồ thị.
- Phân biệt đồ thị ở compile time, link time và runtime.
- Giải thích vai trò của requires, requires transitive, requires static, exports, opens và service binding.
- Biên dịch, chạy và tạo custom runtime image cho một ứng dụng nhiều module.
- Chẩn đoán các lỗi thường gặp khi module graph không hợp lệ hoặc thiếu module.

Ví dụ dùng cú pháp JPMS hiện hành và có thể biên dịch bằng JDK 17 trở lên.

## 1. Đồ thị phụ thuộc trong JPMS là gì?

Mỗi module là một đỉnh (vertex) của đồ thị có hướng. Nếu module A khai báo requires B thì A phụ thuộc vào B và được xem là đọc (reads) B. Ta biểu diễn quan hệ đó bằng cạnh:

~~~text
A ──requires──> B
~~~

Chiều cạnh đi từ module cần phụ thuộc đến module được phụ thuộc. Khi A đọc B, mã trong A có thể sử dụng các kiểu public thuộc những package mà B export cho A. Chỉ có cạnh readability là chưa đủ: package vẫn phải được export và kiểu được sử dụng phải có quyền truy cập phù hợp.

Module descriptor được viết trong module-info.java và được biên dịch thành module-info.class ở gốc của module. Các khai báo requires tạo quan hệ phụ thuộc giữa module; module system dùng chúng để xây dựng readability graph. Đồ thị này có hướng, không đối xứng: nếu A đọc B thì điều đó không tự động có nghĩa B đọc A.

Mọi named module, ngoại trừ chính java.base, đều có phụ thuộc ngầm định vào java.base. Vì vậy module-info.java thường không cần ghi requires java.base.

Ví dụ một ứng dụng có hai module:

~~~text
com.example.app ──requires──> com.example.greeting
       │                                  │
       └──── implicit requires ───────────┤
                                          │
com.example.greeting ── implicit requires ──> java.base
~~~

Trong sơ đồ, cả hai module ứng dụng đều cần java.base; app còn đọc greeting vì khai báo requires com.example.greeting.

## 2. Ba thời điểm và ba cách hình thành đồ thị

### 2.1. Compile time — lúc biên dịch

Công cụ javac cần biết module đang biên dịch phụ thuộc vào những module nào để kiểm tra tên module, kiểu dữ liệu, quyền đọc và quyền truy cập package.

Các nguồn module thường gặp:

- Module source path: nơi chứa mã nguồn của nhiều module, được chỉ định bằng --module-source-path.
- Module path: nơi chứa module đã biên dịch, thường là modular JAR hoặc thư mục module đã bung, được chỉ định bằng --module-path.
- System modules: các module thuộc JDK đang dùng.

Tập root module lúc biên dịch thường là các module được yêu cầu biên dịch. Từ các root này, javac phân giải những phụ thuộc cần thiết để kiểm tra mã nguồn. Đồ thị compile time có thể chỉ là phần tối thiểu đủ cho lần biên dịch đó; không nên mặc định nó luôn giống hoàn toàn đồ thị lúc chạy.

Những kiểm tra quan trọng:

- Module được requires phải tìm thấy trên các đường dẫn module phù hợp.
- Module đang biên dịch phải đọc được module cung cấp kiểu dữ liệu mà nó sử dụng.
- Package được sử dụng phải được module sở hữu export cho module đang đọc.
- requires static vẫn bắt buộc có module tương ứng ở compile time.
- requires transitive làm cho module đọc module hiện tại cũng đọc được dependency được truyền tiếp.

Kết quả của bước này là class file và module descriptor đã biên dịch. javac không tạo một executable độc lập bằng cách gộp toàn bộ dependency vào một file.

### 2.2. Link time — lúc liên kết module

Trong Java, link time thường được nhắc đến khi dùng jlink để tạo custom runtime image. Đây là bước tùy chọn; ứng dụng Java vẫn có thể chạy trên một JDK hoặc runtime image đầy đủ mà không cần tạo image riêng.

jlink nhận:

- Module path chứa các module mà công cụ có thể tìm thấy, chẳng hạn modular JAR, JMOD hoặc exploded module.
- Tập root module chỉ định bằng --add-modules.
- Các phụ thuộc được phân giải từ những root đó.

jlink đưa các root module cùng các dependency cần thiết vào runtime image. Tùy chọn --bind-services yêu cầu công cụ liên kết thêm các module cung cấp service và dependency của chúng. Nhờ đó image có thể nhỏ hơn một JDK đầy đủ nếu ứng dụng chỉ cần một tập module giới hạn.

Điểm cần nhớ:

- Root set của jlink được chỉ định rõ bằng --add-modules.
- Các module được requires thông thường sẽ được đưa vào theo closure phụ thuộc.
- requires static biểu thị dependency tùy chọn ở runtime; chỉ khai báo này không buộc module tùy chọn phải được phân giải.
- Service provider có thể được đưa vào khi dùng service binding.
- jlink tạo runtime image chứa module và runtime cần thiết; nó không biến bytecode Java thành một native executable độc lập.

### 2.3. Runtime — lúc khởi chạy

Khi khởi chạy một ứng dụng dạng named module, java launcher nhận module chính làm root, ví dụ qua --module hoặc -m. Module system tìm module trên system modules và module path, sau đó phân giải các requires cần thiết để hình thành cấu hình module lúc chạy.

Các bước khái quát:

1. Xác định root module của ứng dụng và các root bổ sung nếu có.
2. Tìm module descriptor của từng module trong tập module có thể quan sát.
3. Lần theo các requires cần thiết để xác định những module liên quan.
4. Tính readability graph và kiểm tra xung đột.
5. Tạo cấu hình/layer module để JVM tải lớp khi ứng dụng cần sử dụng.

Việc phân giải module xảy ra trước khi main của ứng dụng bắt đầu. Class loading vẫn diễn ra khi lớp được sử dụng; không có nghĩa JVM phải nạp mọi class trong mọi module ngay tại thời điểm khởi chạy.

Ở runtime, --add-modules có thể bổ sung root module. --limit-modules giới hạn tập module có thể quan sát. Module path và các tùy chọn khởi chạy vì vậy có thể khiến đồ thị runtime khác đồ thị compile time.

### 2.4. So sánh nhanh

| Giai đoạn | Root thường dùng | Công cụ và đầu vào | Kết quả |
|---|---|---|---|
| Compile time | Các module đang biên dịch | javac, module source path, module path, system modules | Class file và module descriptor; graph đủ để kiểm tra biên dịch |
| Link time | Các module ghi trong --add-modules | jlink và module path | Custom runtime image gồm root và dependency được chọn |
| Runtime | Module chính chạy bằng -m/--module | java launcher, system modules và module path | Cấu hình/layer module để JVM thực thi ứng dụng |

Các giai đoạn dùng cùng mô tả module nhưng có root set, đường dẫn và mục tiêu khác nhau. Vì vậy không nên lấy kết quả của javac để kết luận rằng runtime image chắc chắn đã chứa mọi module tùy chọn mà ứng dụng có thể cần.

## 3. Các khai báo ảnh hưởng đến đồ thị

### requires

~~~java
module com.example.app {
    requires com.example.greeting;
}
~~~

com.example.app đọc com.example.greeting. Đây là quan hệ phụ thuộc trực tiếp thông thường; module được yêu cầu phải có mặt khi phân giải ứng dụng ở runtime.

### requires transitive

~~~java
module com.example.api {
    requires transitive com.example.types;
    exports com.example.api;
}
~~~

Dùng requires transitive khi API public của module hiện tại có sử dụng kiểu từ module dependency, chẳng hạn kiểu đó xuất hiện trong tham số, giá trị trả về hoặc superclass của API. Module khác chỉ cần requires com.example.api vẫn có thể đọc com.example.types thông qua quan hệ được truyền tiếp.

Không nên dùng transitive cho mọi dependency. Nếu dependency chỉ được dùng nội bộ trong implementation, requires thông thường thể hiện ranh giới API rõ hơn.

### requires static

~~~java
module com.example.app {
    requires static com.example.optional.annotations;
}
~~~

Dependency này bắt buộc phải có khi biên dịch nhưng có thể vắng mặt khi chạy. Nó phù hợp với một số thư viện annotation hoặc tích hợp tùy chọn. Nếu module vắng mặt ở runtime, mã thực thi không được giả định rằng các class của module đó luôn có thể được tải. Những đường chạy cần dependency phải kiểm tra sự hiện diện hoặc được thiết kế để không kích hoạt phần phụ thuộc khi module không có.

Có thể kết hợp static và transitive khi một dependency vừa tùy chọn ở runtime vừa cần được truyền readability cho module đọc module hiện tại.

### exports và opens

Hai directive này điều khiển quyền truy cập package, không tạo dependency edge:

- exports package: cho phép module khác đọc module này và truy cập các kiểu public trong package được export.
- exports package to moduleA, moduleB: chỉ export package cho các module được nêu tên.
- opens package: cho phép truy cập reflective ở runtime đối với package.
- opens package to moduleA: giới hạn quyền reflective cho module được chỉ định.
- open module: mở tất cả package của module cho reflective access ở runtime.

Một package không được export thì module khác không thể dùng API public trong package đó chỉ bằng cách thêm import. Với reflection, opens giải quyết quyền truy cập ở runtime; nó không thay thế requires.

### uses, provides và service binding

Module có thể khai báo uses để tiêu thụ một service và provides ... with ... để cung cấp implementation. Đây là quan hệ service, khác với requires trực tiếp. Khi tạo runtime image, --bind-services cho phép jlink tìm provider module và đưa provider cùng dependency của nó vào image. Khi chạy, ServiceLoader tìm provider trong module layer phù hợp.

## 4. Ví dụ chạy được với hai module

Tạo cấu trúc thư mục:

~~~text
module-demo/
└── src/
    ├── com.example.greeting/
    │   ├── module-info.java
    │   └── com/example/greeting/Greeting.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java
~~~

Module cung cấp lời chào, file src/com.example.greeting/module-info.java:

~~~java
module com.example.greeting {
    exports com.example.greeting;
}
~~~

File src/com.example.greeting/com/example/greeting/Greeting.java:

~~~java
package com.example.greeting;

public class Greeting {
    public static String message() {
        return "Hello from JPMS";
    }
}
~~~

Module ứng dụng khai báo dependency, file src/com.example.app/module-info.java:

~~~java
module com.example.app {
    requires com.example.greeting;
}
~~~

File src/com.example.app/com/example/app/Main.java:

~~~java
package com.example.app;

import com.example.greeting.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
~~~

### Biên dịch

Chạy từ thư mục module-demo:

~~~bash
javac -d out --module-source-path src -m com.example.greeting,com.example.app
~~~

--module-source-path cho javac biết nơi tìm mã nguồn theo cấu trúc module. -m chỉ định hai module cần biên dịch. Kết quả được đặt trong out/com.example.greeting và out/com.example.app; mỗi module có module-info.class.

### Chạy trực tiếp từ exploded modules

~~~bash
java --module-path out --module com.example.app/com.example.app.Main
~~~

Kết quả stdout:

~~~text
Hello from JPMS
~~~

Đồ thị của ví dụ:

~~~text
com.example.app ──requires──> com.example.greeting
       │                                  │
       └──── implicit requires ──> java.base
                                          ▲
                                          │
                     implicit requires ──┘
                     từ com.example.greeting
~~~

com.example.app cần com.example.greeting để gọi Greeting.message(). Cả hai module đều có dependency ngầm định vào java.base.

## 5. Tạo runtime image bằng jlink

Đây là bước link tùy chọn sau khi đã biên dịch. Đóng gói từng module thành modular JAR:

~~~bash
mkdir mods
jar --create --file mods/com.example.greeting.jar -C out/com.example.greeting .
jar --create --file mods/com.example.app.jar -C out/com.example.app .
~~~

Tạo runtime image với ứng dụng làm root:

~~~bash
jlink --module-path mods --add-modules com.example.app --output runtime-image
~~~

jlink tìm com.example.app, đọc module descriptor, lần theo requires com.example.greeting và các dependency của chúng. java.base được đưa vào do dependency ngầm định của các named module. Nếu ứng dụng sử dụng service provider và muốn liên kết provider vào image, có thể thêm --bind-services.

Chạy bằng launcher trong image:

~~~bash
runtime-image/bin/java --module com.example.app/com.example.app.Main
~~~

Trên Windows PowerShell:

~~~powershell
.\runtime-image\bin\java.exe --module com.example.app/com.example.app.Main
~~~

Kết quả stdout vẫn là:

~~~text
Hello from JPMS
~~~

Có thể xem danh sách module trong image bằng:

~~~bash
runtime-image/bin/java --list-modules
~~~

Danh sách cụ thể phụ thuộc vào JDK và các dependency thực tế. Với ví dụ tối giản, image cần hai module ứng dụng cùng java.base.

Runtime image được tạo cho nền tảng hệ điều hành và kiến trúc tương ứng. Đội phát triển chịu trách nhiệm tạo và cập nhật lại image khi JDK hoặc dependency của ứng dụng thay đổi.

## 6. Những lỗi thường gặp và cách xác định nguyên nhân

### Không tìm thấy module

Thông báo thường gặp là java.lang.module.FindException: Module ... not found. Nguyên nhân thường là thiếu module trên --module-path, sai tên module trong requires, hoặc đường dẫn trỏ đến thư mục không chứa module hợp lệ.

Cách kiểm tra: xác nhận tên module bằng jar --describe-module và kiểm tra lại module path của cả lệnh biên dịch lẫn lệnh chạy.

### Module không đọc được hoặc package không được export

javac có thể báo package không visible khi module hiện tại chưa requires module cung cấp package, hoặc module dependency chưa export package đó. Thêm import không tạo ra quan hệ readability và cũng không mở package.

Cách xử lý: sửa module-info.java ở đúng module sở hữu dependency hoặc export package cần công khai. Chỉ export những package thuộc API mà module muốn cung cấp.

### Đồ thị có xung đột

Resolution có thể thất bại khi có vòng phụ thuộc requires, khi một module đọc nhiều module cùng tên, hoặc khi hai module cùng export một package cho module đọc cả hai. Tên module phải duy nhất trong cấu hình và package được chia ranh giới module rõ ràng.

### Biên dịch được nhưng runtime thiếu dependency tùy chọn

requires static cho phép dependency vắng mặt ở runtime. Nếu đường chạy vẫn cố tải hoặc gọi class của dependency đã vắng mặt, ứng dụng có thể gặp lỗi tải lớp. Hãy kiểm tra điều kiện kích hoạt phần tích hợp tùy chọn và xác nhận module cần thiết có được đưa vào runtime image hay không.

### Chạy nhầm classpath và module path

Class trên classpath thuộc unnamed module; nó không tự trở thành named module chỉ vì JAR có package. Khi muốn chạy ứng dụng JPMS, hãy đặt modular JAR hoặc exploded module lên --module-path và chỉ định root bằng --module/-m.

## 7. Công cụ quan sát và kiểm tra đồ thị

Các lệnh sau giúp kiểm tra module descriptor và cấu hình:

~~~bash
# Xem descriptor của một modular JAR
jar --describe-module --file mods/com.example.app.jar

# Hiển thị các module được phân giải khi khởi chạy
java --show-module-resolution --module-path out --module com.example.app/com.example.app.Main

# Kiểm tra xung đột trong các module có trên module path
java --validate-modules --module-path out

# Phân tích dependency module mà một JAR cần
jdeps --print-module-deps app.jar

# Liệt kê các module có thể quan sát trong runtime hiện tại
java --list-modules
~~~

--show-module-resolution hữu ích khi cần biết module nào được chọn và quan hệ requires nào đã được phân giải. --validate-modules giúp phát hiện xung đột trước khi chạy ứng dụng. jdeps hỗ trợ phân tích dependency từ bytecode; kết quả cần được đối chiếu với module descriptor và cấu hình thực tế.

## 8. Nguyên tắc thiết kế thực tế

- Khai báo dependency trực tiếp mà module thực sự sử dụng bằng requires.
- Chỉ dùng requires transitive khi kiểu của dependency là một phần API public mà consumer cần đọc.
- Dùng requires static cho dependency thật sự tùy chọn ở runtime và bảo đảm code xử lý trường hợp dependency vắng mặt.
- Export package có chủ đích; không export package nội bộ chỉ để chữa lỗi truy cập.
- Phân biệt package access thông thường với reflective access: exports dành cho API, opens dành cho reflection.
- Với ServiceLoader, khai báo uses/provides rõ ràng và kiểm tra service provider có được đưa vào runtime image hay không.
- Kiểm tra module path riêng cho compile, runtime và jlink. Ba lệnh có thể dùng các tập module khác nhau.
- Chạy thử bằng đúng JDK và runtime image dự kiến phát hành; một lần biên dịch thành công chưa chứng minh image cuối cùng có đủ module.

## Tóm tắt

Đồ thị phụ thuộc JPMS được hình thành từ các module descriptor và tập root của từng giai đoạn. Compile time giúp javac kiểm tra source và readability; link time với jlink chọn module cần đóng gói vào custom runtime image; runtime phân giải module chính cùng dependency trước khi thực thi main. requires tạo dependency edge, requires transitive truyền readability, requires static làm dependency tùy chọn ở runtime, còn exports/opens kiểm soát quyền truy cập package. Hiểu đúng các khác biệt này giúp thiết kế ranh giới module rõ ràng và tránh lỗi chỉ xuất hiện khi đóng gói hoặc triển khai.

## Tài liệu tham khảo chính thức

- [Java Platform Module System — java.lang.module](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/package-summary.html)
- [Java Language Specification, Chapter 7: Packages and Modules](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html)
- [The javac Command — JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [The java Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [The jlink Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)
- [Optional Dependencies with requires static — Dev.java](https://dev.java/learn/organizing/modules/optional-dependencies/)
