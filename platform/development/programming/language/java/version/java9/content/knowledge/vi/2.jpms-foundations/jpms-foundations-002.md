# Mã nguồn, package và tài nguyên bên trong một mô-đun

Trong JPMS (Java Platform Module System), một mô-đun có thể chứa nhiều package, các lớp Java và những tài nguyên đi kèm như tệp cấu hình, mẫu hoặc dữ liệu tĩnh. Mô-đun là đơn vị đóng gói và kiểm soát phụ thuộc; package là đơn vị tổ chức tên và phạm vi truy cập trong mã nguồn; tài nguyên là dữ liệu được đóng gói cùng mô-đun. Hiểu rõ ba phần này giúp thiết kế API công khai gọn, giữ phần triển khai nội bộ được đóng kín và đọc tài nguyên ổn định khi ứng dụng chạy từ mô-đun hoặc JAR.

## 1. Ba thành phần bên trong mô-đun

- **Mã nguồn Java** là các tệp `.java` khai báo class, interface, enum, record và các kiểu khác. Mỗi tệp thường khai báo package ở đầu tệp.
- **Package** gom các kiểu có liên quan vào một không gian tên. Package giúp tránh trùng tên, tổ chức mã và áp dụng quyền truy cập ở mức package.
- **Tài nguyên** là tệp không phải mã Java, ví dụ `properties`, `json`, `xml`, mẫu HTML hoặc dữ liệu văn bản. Tài nguyên được lưu theo đường dẫn bên trong mô-đun và có thể được đóng gói vào đầu ra build hoặc JAR.

Mỗi named module có một mô tả mô-đun ở `module-info.java`. Tệp này khai báo tên mô-đun và các quan hệ cần thiết như `requires`, `exports`, `opens`, `uses` hoặc `provides`. Nó không chứa class nghiệp vụ và không có khai báo package như tệp Java thông thường.

Một mô-đun có thể chứa nhiều package. Tên package thường dùng tiền tố theo tên miền đảo ngược, chẳng hạn `com.example.greetings.api`, nhưng tên package và tên mô-đun là hai định danh riêng. Việc dùng cùng tiền tố giúp người đọc nhận ra các package thuộc cùng một mô-đun; JPMS không yêu cầu chúng phải giống nhau.

## 2. Cấu trúc mã nguồn và vị trí của module-info.java

Với cấu trúc nguồn thường dùng trong Maven hoặc Gradle, một mô-đun có thể được tổ chức như sau:

```text
greetings/
└── src/
    └── main/
        ├── java/
        │   ├── module-info.java
        │   └── com/
        │       └── example/
        │           └── greetings/
        │               ├── api/
        │               │   ├── GreetingService.java
        │               │   └── GreetingServices.java
        │               ├── internal/
        │               │   └── DefaultGreetingService.java
        │               └── app/
        │                   └── Main.java
        └── resources/
            └── com/
                └── example/
                    └── greetings/
                        └── app/
                            └── banner.txt
```

Trong cấu trúc này:

- `module-info.java` nằm ở gốc source root `src/main/java`, cùng cấp với thư mục package `com`.
- Đường dẫn thư mục thường phản ánh tên package. Ví dụ, `com/example/greetings/api/GreetingService.java` khai báo `package com.example.greetings.api;`.
- `api` chứa các kiểu mà mô-đun muốn cung cấp cho mô-đun khác.
- `internal` chứa chi tiết triển khai chỉ cần dùng bên trong mô-đun.
- `app` chứa điểm khởi chạy hoặc phần điều phối của ví dụ.
- `src/main/resources` chứa dữ liệu không phải mã Java. Khi build, công cụ build sao chép các tệp này vào đầu ra của mô-đun và giữ nguyên đường dẫn tương đối.

Cấu trúc thư mục là quy ước của công cụ build và cách tổ chức dự án. Điều quan trọng đối với JPMS là các tệp Java được biên dịch thành một mô-đun có descriptor hợp lệ và các package được khai báo đúng. Tên thư mục không tự tạo ra package; câu lệnh `package` trong mã nguồn mới xác định tên package của kiểu.

Một named module cần dùng package có tên. Không đặt class của mô-đun trong default package (package không có tên), vì kiểu trong default package không phù hợp với cấu trúc mô-đun có tên. Tên package phân biệt chữ hoa và chữ thường; hãy giữ cách viết nhất quán giữa khai báo, import và đường dẫn tài nguyên.

## 3. Package và ranh giới API của mô-đun

Package và mô-đun kiểm soát hai lớp truy cập khác nhau:

1. Quy tắc truy cập của Java quyết định mã nào có thể dùng kiểu hoặc thành viên: `public`, `protected`, package-private và `private`.
2. JPMS quyết định package nào của mô-đun được phép truy cập từ mô-đun khác thông qua `exports` hoặc được mở cho reflection thông qua `opens`.

Một kiểu `public` không tự động trở thành API của toàn ứng dụng. Nếu package chứa kiểu đó không được mô-đun xuất ra, mô-đun khác không thể sử dụng kiểu ấy qua ranh giới JPMS. Ngược lại, mã ở bên trong cùng mô-đun vẫn có thể dùng package nội bộ theo các quy tắc truy cập Java thông thường.

Ví dụ descriptor chỉ xuất package API:

```java
module com.example.greetings {
    exports com.example.greetings.api;
}
```

Khai báo trên cho phép mô-đun khác đọc và sử dụng các kiểu `public` trong `com.example.greetings.api`, với điều kiện mô-đun tiêu thụ có khai báo phụ thuộc phù hợp. Package `com.example.greetings.internal` không được xuất nên phần triển khai trong đó không trở thành API công khai.

Mô-đun tiêu thụ có thể khai báo:

```java
module com.example.client {
    requires com.example.greetings;
}
```

Sau đó mã của client có thể import `com.example.greetings.api.GreetingService` hoặc `GreetingServices`. Client không thể import `com.example.greetings.internal.DefaultGreetingService` chỉ vì class triển khai được khai báo `public`; package `internal` chưa được xuất.

Có thể dùng qualified export khi chỉ một số mô-đun được phép dùng API:

```java
module com.example.greetings {
    exports com.example.greetings.api to com.example.client;
}
```

Khi đó package được xuất có giới hạn cho mô-đun được nêu tên. Chỉ dùng cách này khi danh sách mô-đun tiêu thụ là một phần có chủ đích của thiết kế.

Một số nguyên tắc tổ chức package:

- Chỉ xuất những package tạo thành hợp đồng mà mô-đun cam kết hỗ trợ.
- Để class triển khai, helper và chi tiết nội bộ trong package không xuất.
- Không coi package con là package tự động được xuất. `exports com.example.greetings.api;` không xuất `com.example.greetings.api.internal`.
- Không để nhiều named module cùng sở hữu một package name trong cùng cấu hình mô-đun. Split package gây xung đột khi phân giải mô-đun và làm ranh giới sở hữu package khó hiểu.
- Giữ package theo trách nhiệm và API ổn định; không tạo package chỉ để chia nhỏ thư mục một cách hình thức.

## 4. Ví dụ hoàn chỉnh: API, triển khai nội bộ và tài nguyên

Ví dụ sau tạo một named module `com.example.greetings`. Mô-đun xuất package API, giữ class triển khai trong package nội bộ và đọc một tệp văn bản được đóng gói cùng mô-đun.

Cấu trúc tệp cần có:

```text
src/main/java/module-info.java
src/main/java/com/example/greetings/api/GreetingService.java
src/main/java/com/example/greetings/api/GreetingServices.java
src/main/java/com/example/greetings/internal/DefaultGreetingService.java
src/main/java/com/example/greetings/app/Main.java
src/main/resources/com/example/greetings/app/banner.txt
```

**Descriptor `module-info.java`:**

```java
module com.example.greetings {
    exports com.example.greetings.api;
}
```

**Hợp đồng API `GreetingService.java`:**

```java
package com.example.greetings.api;

public interface GreetingService {
    String greet(String name);
}
```

**Điểm tạo đối tượng công khai `GreetingServices.java`:**

```java
package com.example.greetings.api;

import com.example.greetings.internal.DefaultGreetingService;

public final class GreetingServices {

    private GreetingServices() {
    }

    public static GreetingService create() {
        return new DefaultGreetingService();
    }
}
```

Factory nằm trong package API và trả về interface. Mã tiêu thụ chỉ cần biết hợp đồng `GreetingService`; nó không cần biết class triển khai cụ thể.

**Triển khai nội bộ `DefaultGreetingService.java`:**

```java
package com.example.greetings.internal;

import com.example.greetings.api.GreetingService;

public final class DefaultGreetingService implements GreetingService {

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

Class triển khai được khai báo `public` để có thể được sử dụng từ package khác bên trong cùng mô-đun. Package `internal` không được xuất, vì vậy mô-đun khác không thể phụ thuộc trực tiếp vào class này.

**Điểm chạy và đọc tài nguyên `Main.java`:**

```java
package com.example.greetings.app;

import com.example.greetings.api.GreetingService;
import com.example.greetings.api.GreetingServices;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class Main {

    private Main() {
    }

    public static void main(String[] args) throws IOException {
        GreetingService service = GreetingServices.create();
        System.out.println(service.greet("JPMS"));

        try (InputStream stream =
                     Main.class.getResourceAsStream("banner.txt")) {
            if (stream == null) {
                throw new IllegalStateException("Missing banner.txt");
            }

            String banner =
                    new String(stream.readAllBytes(), StandardCharsets.UTF_8);
            System.out.println(banner);
        }
    }
}
```

**Nội dung `banner.txt`:**

```text
Resources are packaged with the module.
```

Vì `banner.txt` nằm cùng đường dẫn package với `Main`, lời gọi `Main.class.getResourceAsStream("banner.txt")` tìm tệp tương đối từ package `com.example.greetings.app`. Mã đang chạy bên trong chính mô-đun nên có thể đọc tài nguyên của package đó.

Có thể biên dịch và chạy ví dụ bằng JDK 17 trở lên. Các lệnh dưới đây dùng PowerShell và giả định đang đứng tại thư mục dự án:

```powershell
javac -d out src/main/java/module-info.java src/main/java/com/example/greetings/api/GreetingService.java src/main/java/com/example/greetings/api/GreetingServices.java src/main/java/com/example/greetings/internal/DefaultGreetingService.java src/main/java/com/example/greetings/app/Main.java
New-Item -ItemType Directory -Force out/com/example/greetings/app
Copy-Item src/main/resources/com/example/greetings/app/banner.txt out/com/example/greetings/app/banner.txt
java --module-path out -m com.example.greetings/com.example.greetings.app.Main
```

Lệnh `javac` biên dịch descriptor và các lớp vào `out`. Trình biên dịch không tự sao chép `banner.txt`, vì vậy lệnh `Copy-Item` đặt tài nguyên vào đúng đường dẫn trong đầu ra mô-đun. Khi chạy, `--module-path out` chỉ vị trí mô-đun và `-m` chỉ rõ mô-đun cùng class chứa phương thức `main`.

Kết quả chuẩn:

```text
Hello, JPMS!
Resources are packaged with the module.
```

## 5. Tài nguyên được lưu và truy cập như thế nào?

Tài nguyên không phải class và không được khai báo bằng câu lệnh `package`. Chúng được nhận diện bằng đường dẫn tương đối trong đầu ra mô-đun hoặc trong JAR. Ví dụ, tệp nguồn:

```text
src/main/resources/com/example/greetings/app/banner.txt
```

được đặt trong đầu ra tại:

```text
com/example/greetings/app/banner.txt
```

Khi đóng gói thành modular JAR, đường dẫn này được giữ bên trong JAR cùng với các class và `module-info.class`. Vì vậy, không nên dựa vào đường dẫn tương đối của thư mục làm việc như `new File("banner.txt")`: cách đó phụ thuộc nơi tiến trình được khởi chạy và có thể hỏng khi ứng dụng chạy từ JAR.

Hai cách viết phổ biến với `Class`:

```java
// Đường dẫn tương đối từ package của lớp Main.
Main.class.getResourceAsStream("banner.txt");

// Đường dẫn tuyệt đối từ gốc tài nguyên của mô-đun.
Main.class.getResourceAsStream(
        "/com/example/greetings/app/banner.txt");
```

Với `Class.getResourceAsStream`, đường dẫn không có dấu `/` ở đầu được hiểu tương đối từ package của class; đường dẫn có dấu `/` ở đầu được hiểu từ gốc tài nguyên. Hãy chọn một quy ước rõ ràng và giữ đường dẫn nhất quán với cấu trúc tài nguyên.

Khi đọc bằng `InputStream`, nên:

- Kiểm tra kết quả `null` để phát hiện tệp không tồn tại hoặc không truy cập được.
- Dùng `try-with-resources` để đóng stream.
- Chỉ định charset, thường là `StandardCharsets.UTF_8`, khi chuyển byte thành văn bản.
- Không giả định tài nguyên là một tệp vật lý có thể sửa trực tiếp. Khi chạy từ JAR, tài nguyên nằm trong archive; hãy đọc qua API tài nguyên.

### Quyền truy cập tài nguyên qua ranh giới mô-đun

`exports` và `opens` có mục đích khác nhau:

- `exports` cho phép mô-đun khác truy cập các kiểu `public` trong package thông qua mã Java thông thường.
- `opens` cho phép truy cập sâu bằng reflection tại runtime đối với package được mở. Quyền này cũng liên quan đến khả năng truy cập tài nguyên không phải class trong package từ mô-đun khác.

Do đó, xuất một package không đồng nghĩa với việc mở package đó cho reflection hoặc làm mọi tài nguyên bên trong tự động truy cập được. Nếu một framework hoặc mô-đun khác thực sự cần truy cập reflection vào package cụ thể, hãy mở đúng package cho đúng mô-đun:

```java
module com.example.greetings {
    exports com.example.greetings.api;
    opens com.example.greetings.model to com.example.json;
}
```

Ví dụ trên giả định package `com.example.greetings.model` tồn tại và mô-đun `com.example.json` là bên cần quyền reflection. Không thêm `opens` chỉ vì một package có class `public`; chỉ mở khi có nhu cầu runtime cụ thể. Mở toàn bộ mô-đun làm giảm mức đóng gói nên cần được cân nhắc kỹ.

## 6. Kiểm tra nội dung mô-đun sau khi build

Sau khi build hoặc đóng gói, có thể dùng công cụ JDK để kiểm tra artifact:

```powershell
jar --describe-module --file build/libs/greetings.jar
jar --list --file build/libs/greetings.jar
```

- `jar --describe-module` hiển thị descriptor mà JDK nhận diện từ artifact, gồm tên mô-đun và các package được xuất.
- `jar --list` hiển thị các entry trong archive. Có thể dùng nó để xác nhận `module-info.class`, class đã biên dịch và tài nguyên mong đợi đều được đóng gói.

Tên và vị trí JAR trong ví dụ phụ thuộc cấu hình build của dự án. Nếu build tool tạo thư mục đầu ra khác, thay đường dẫn cho đúng artifact thực tế.

## 7. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Mô-đun khác không import được class `public` | Package chứa class chưa được `exports` | Xuất đúng package API trong `module-info.java`, rồi kiểm tra mô-đun tiêu thụ có `requires` |
| Client truy cập được interface nhưng không dùng được class triển khai | Package triển khai không được xuất | Đây thường là kết quả mong muốn; client dùng interface/factory công khai |
| Reflection bị từ chối ở runtime | Package chưa được mở cho mô-đun cần reflection | Dùng `opens package.name to consumer.module;` khi thật sự cần |
| `getResourceAsStream` trả về `null` | Sai đường dẫn, sai chữ hoa/thường, tài nguyên chưa được copy hoặc package bị đóng với caller bên ngoài | Kiểm tra entry trong output/JAR, đường dẫn tương đối và quyền mở package |
| Chạy được trong IDE nhưng lỗi khi chạy JAR | Tài nguyên được đọc bằng đường dẫn filesystem phụ thuộc thư mục làm việc | Đọc bằng `Class.getResourceAsStream` hoặc API tài nguyên phù hợp |
| Trình biên dịch báo package không tồn tại trong module | Khai báo package, đường dẫn nguồn hoặc descriptor không nhất quán | Kiểm tra câu lệnh `package`, vị trí source root và package được khai báo trong module |
| Hai mô-đun xung đột package | Cùng một package name được đặt trong nhiều named module | Chọn một mô-đun sở hữu package và chuyển kiểu liên quan về đúng mô-đun |

## 8. Checklist thiết kế

Trước khi hoàn tất một mô-đun, hãy kiểm tra:

- `module-info.java` nằm ở gốc source root và khai báo đúng tên mô-đun.
- Mỗi tệp Java khai báo package có tên phù hợp; không dùng default package.
- Package API được xuất có chủ đích; package triển khai được giữ nội bộ.
- Mô-đun tiêu thụ khai báo `requires` cho mô-đun mà nó sử dụng.
- Chỉ dùng `opens` cho nhu cầu reflection hoặc truy cập tài nguyên runtime đã xác định.
- Tài nguyên nằm trong source set tài nguyên và được build tool đưa vào artifact.
- Mã đọc tài nguyên dùng đường dẫn trong module/JAR, kiểm tra trường hợp không tìm thấy và đóng stream.
- Artifact sau build chứa descriptor, class và tài nguyên đúng vị trí.

Một mô-đun được tổ chức tốt có package API nhỏ và ổn định, package triển khai được đóng kín, còn tài nguyên có đường dẫn rõ ràng và được đọc qua API phù hợp. Cách tổ chức đó giữ hợp đồng giữa các mô-đun dễ hiểu và giúp ứng dụng hoạt động nhất quán khi chạy từ thư mục build hoặc từ modular JAR.
