# Tổ chức đầu ra dạng thư mục mô-đun trong Java

Khi biên dịch một ứng dụng Java dùng JPMS (Java Platform Module System), đầu ra nên được tổ chức thành **một thư mục riêng cho mỗi mô-đun**. Cấu trúc này giữ nguyên ranh giới mô-đun sau khi biên dịch: mỗi thư mục mô-đun có `module-info.class` ở thư mục gốc và các file `.class` nằm dưới đường dẫn package tương ứng.

Với `javac`, hai tùy chọn quan trọng là:

- `--module-source-path`: chỉ định thư mục gốc chứa mã nguồn của nhiều mô-đun.
- `-d`: chỉ định thư mục gốc để ghi các file đã biên dịch.

Ví dụ, nếu mã nguồn nằm trong `src/` và đầu ra nằm trong `out/`, sau khi biên dịch hai mô-đun, ta nhận được `out/com.acme.greeter/` và `out/com.acme.app/`. Mỗi thư mục là một *exploded module* (mô-đun đã giải nén), có thể được đưa trực tiếp lên module path để chạy.

## 1. Phân biệt thư mục nguồn và thư mục đầu ra

Một dự án nhiều mô-đun có thể được tổ chức như sau:

```text
project/
├── src/
│   ├── com.acme.greeter/
│   │   ├── module-info.java
│   │   └── com/acme/greeter/api/Greeter.java
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
├── out/
└── dist/
```

Trong cấu trúc này:

- `src/` là module source path root. Mỗi thư mục con trực tiếp đại diện cho tên một mô-đun.
- `src/com.acme.greeter/module-info.java` khai báo mô-đun `com.acme.greeter`.
- `src/com.acme.app/module-info.java` khai báo mô-đun `com.acme.app`.
- Các thư mục bên dưới `module-info.java` tuân theo đường dẫn package, ví dụ `com/acme/greeter/api/`.
- `out/` là nơi chứa kết quả biên dịch; không phải thư mục nguồn và cũng không đại diện cho một mô-đun duy nhất.
- `dist/` có thể chứa các gói triển khai như modular JAR sau khi đóng gói.

Tên thư mục mô-đun nên khớp với tên được khai báo trong `module-info.java`. Tên mô-đun được xác định bởi module descriptor đã biên dịch, không chỉ bởi tên thư mục hoặc tên file JAR.

## 2. Cấu trúc đầu ra do `javac -d` tạo ra

Giả sử có hai mô-đun:

**Mô-đun thư viện — `src/com.acme.greeter/module-info.java`:**

```java
module com.acme.greeter {
    exports com.acme.greeter.api;
}
```

**API của thư viện — `src/com.acme.greeter/com/acme/greeter/api/Greeter.java`:**

```java
package com.acme.greeter.api;

public final class Greeter {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

**Mô-đun ứng dụng — `src/com.acme.app/module-info.java`:**

```java
module com.acme.app {
    requires com.acme.greeter;
}
```

**Điểm chạy của ứng dụng — `src/com.acme.app/com/acme/app/Main.java`:**

```java
package com.acme.app;

import com.acme.greeter.api.Greeter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(new Greeter().greet("JPMS"));
    }
}
```

Từ thư mục gốc của dự án, tạo một thư mục đầu ra rỗng rồi biên dịch cả hai mô-đun:

**PowerShell:**

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --module-source-path src -d out -m com.acme.greeter,com.acme.app
```

**Bash:**

```bash
mkdir -p out
javac --module-source-path src -d out -m com.acme.greeter,com.acme.app
```

Ý nghĩa các tùy chọn:

- `--module-source-path src` nói với trình biên dịch rằng `src` chứa các thư mục mã nguồn mô-đun.
- `-d out` đặt thư mục gốc cho kết quả biên dịch.
- `-m com.acme.greeter,com.acme.app` yêu cầu biên dịch hai mô-đun được nêu tên. Trình biên dịch xử lý các quan hệ phụ thuộc giữa chúng theo module descriptor.

Sau khi biên dịch, cấu trúc đầu ra có dạng:

```text
out/
├── com.acme.greeter/
│   ├── module-info.class
│   └── com/acme/greeter/api/Greeter.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
```

Điểm quan trọng là `module-info.class` nằm ở **gốc của từng thư mục mô-đun**. Các lớp được đặt dưới thư mục package bên trong mô-đun tương ứng. Không đặt tất cả `module-info.class` ở ngay `out/`, vì nhiều mô-đun cần module descriptor riêng.

Thư mục `out/com.acme.greeter/` và `out/com.acme.app/` là hai exploded modules. Các file nguồn `.java` không được sao chép sang đây; đầu ra chủ yếu gồm bytecode `.class` và module descriptor `.class`.

## 3. Chạy ứng dụng từ các thư mục mô-đun

Vì `out/` chứa các thư mục mô-đun đã biên dịch, có thể dùng trực tiếp nó làm module path:

```bash
java --module-path out -m com.acme.app/com.acme.app.Main
```

Trong lệnh trên:

- `--module-path out` cung cấp vị trí các mô-đun có thể được phân giải.
- `-m com.acme.app/com.acme.app.Main` chọn mô-đun gốc `com.acme.app` và lớp chính `com.acme.app.Main`.
- Khi phân giải `com.acme.app`, runtime đọc module descriptor và tìm `com.acme.greeter` vì ứng dụng khai báo `requires com.acme.greeter;`.

Kết quả chạy:

```text
Hello, JPMS!
```

Trên Windows PowerShell, lệnh chạy tương tự:

```powershell
java --module-path out -m com.acme.app/com.acme.app.Main
```

Có thể dùng `--module` thay cho dạng rút gọn `-m`:

```bash
java --module-path out --module com.acme.app/com.acme.app.Main
```

Module path phải trỏ đến vị trí mà runtime có thể tìm thấy mô-đun. Trong ví dụ này, trỏ đến `out/` là đúng vì các thư mục con trực tiếp của nó là các exploded modules. Trỏ vào `out/com.acme.app/com/acme/app/` là sai: đó là thư mục package/class, không phải gốc mô-đun.

## 4. Đóng gói một thư mục mô-đun thành modular JAR

Thư mục mô-đun đã biên dịch có thể chạy trực tiếp, hoặc có thể đóng gói thành modular JAR để phân phối. Ví dụ, đóng gói riêng mô-đun thư viện:

**PowerShell:**

```powershell
New-Item -ItemType Directory -Force dist | Out-Null
jar --create --file dist/com.acme.greeter.jar -C out/com.acme.greeter .
```

**Bash:**

```bash
mkdir -p dist
jar --create --file dist/com.acme.greeter.jar -C out/com.acme.greeter .
```

Tùy chọn `-C out/com.acme.greeter .` chuyển thư mục làm việc của lệnh `jar` vào gốc mô-đun đã biên dịch rồi đưa nội dung tại đó vào JAR. Vì vậy, `module-info.class` được đặt ở gốc JAR, bên cạnh cấu trúc package, giúp JAR giữ module descriptor.

Có thể kiểm tra descriptor trong JAR:

```bash
jar --describe-module --file dist/com.acme.greeter.jar
```

Với ví dụ trên, thông tin chính có dạng:

```text
com.acme.greeter
exports com.acme.greeter.api
requires java.base mandated
```

Sau khi đóng gói thư viện, có thể đặt JAR và thư mục mô-đun ứng dụng trên cùng module path. Ví dụ dưới đây dùng JAR cho thư viện và exploded module cho ứng dụng:

**PowerShell:**

```powershell
java --module-path "dist/com.acme.greeter.jar;out/com.acme.app" -m com.acme.app/com.acme.app.Main
```

**Bash:**

```bash
java --module-path "dist/com.acme.greeter.jar:out/com.acme.app" -m com.acme.app/com.acme.app.Main
```

Kết quả vẫn là:

```text
Hello, JPMS!
```

Lưu ý ký tự phân tách nhiều phần tử của module path phụ thuộc hệ điều hành: Windows dùng dấu chấm phẩy `;`, còn Linux/macOS dùng dấu hai chấm `:`.

## 5. Exploded module, modular JAR và classpath

Ba cách tổ chức thường gặp có mục đích khác nhau:

| Dạng | Cấu trúc | Cách sử dụng |
|---|---|---|
| Exploded module | Thư mục mô-đun chứa `module-info.class` và các package class | Đặt thư mục mô-đun hoặc thư mục cha chứa các mô-đun lên module path. |
| Modular JAR | JAR có `module-info.class` ở gốc | Đặt file JAR lên module path. |
| Classpath | Các thư mục/JAR được nạp vào unnamed module | Dùng cho mã chạy theo classpath, không áp dụng đầy đủ ranh giới named module như ví dụ JPMS này. |

Một thư mục chứa nhiều exploded modules là cách tổ chức đầu ra thuận tiện trong quá trình phát triển và kiểm thử. Modular JAR thường phù hợp khi cần đóng gói từng mô-đun để phân phối hoặc triển khai.

Không nên nhầm `out/` với classpath chỉ vì nó là thư mục. Ý nghĩa của nó phụ thuộc vào cách runtime sử dụng nó: khi truyền cho `--module-path`, runtime tìm các mô-đun theo cấu trúc và module descriptor; khi truyền cho `--class-path`, nội dung được xử lý theo cơ chế classpath.

## 6. Lỗi thường gặp khi tổ chức thư mục đầu ra

**Đặt sai module source path**

Nếu dùng `--module-source-path src/com.acme.app` trong khi dự án có nhiều mô-đun nằm cạnh nhau, trình biên dịch không còn nhìn thấy toàn bộ cấu trúc nguồn như dự định. Hãy đặt module source path ở thư mục gốc chung, chẳng hạn `src`.

**Thiếu `module-info.java` ở gốc thư mục nguồn mô-đun**

Với named module tường minh, file descriptor nằm trực tiếp trong `src/<module-name>/module-info.java`. Không đặt file này dưới thư mục package.

**Đặt sai tên thư mục mô-đun hoặc tên khai báo**

Tên thư mục nguồn nên khớp với tên trong `module-info.java`. Khi chạy, dùng đúng tên mô-đun đã khai báo, ví dụ `com.acme.app`.

**Đặt module path vào thư mục package**

Module path phải trỏ đến gốc exploded module hoặc vị trí chứa các mô-đun. Đường dẫn package như `out/com.acme.app/com/acme/app` không phải gốc mô-đun.

**Đầu ra cũ còn sót lại**

Biên dịch vào thư mục đã chứa kết quả cũ có thể để lại các class không còn tương ứng với mã nguồn hiện tại. Trong quy trình build, dùng thư mục đầu ra sạch hoặc tác vụ clean của build tool trước khi biên dịch lại. Không dùng thư mục chứa dữ liệu nguồn hay tài liệu làm thư mục đích `-d`.

**Nhầm `-d` với `--module-path`**

`-d` là nơi `javac` ghi file đầu ra. `--module-path` là nơi trình biên dịch hoặc runtime tìm các mô-đun phụ thuộc. Hai đường dẫn có thể trỏ đến các vị trí khác nhau và giải quyết hai công việc khác nhau.

## 7. Checklist kiểm tra cấu trúc đầu ra

Trước khi chạy ứng dụng mô-đun, hãy xác nhận:

1. Mỗi mô-đun có thư mục nguồn riêng dưới module source path root.
2. `module-info.java` nằm ngay trong thư mục gốc của mô-đun nguồn.
3. Lệnh biên dịch dùng `--module-source-path` trỏ đến thư mục gốc chung.
4. Lệnh `javac` dùng `-d` trỏ đến thư mục đầu ra riêng và sạch.
5. Sau khi biên dịch, mỗi thư mục mô-đun trong output có `module-info.class` ở gốc.
6. Các file class nằm dưới đúng đường dẫn package.
7. Lệnh chạy dùng `--module-path` trỏ đến exploded modules hoặc modular JAR.
8. Tên mô-đun và tên lớp chính trong `-m` khớp với module descriptor và package thực tế.

Giữ thư mục nguồn, thư mục đầu ra và thư mục phân phối tách biệt giúp cấu trúc JPMS rõ ràng ở cả lúc biên dịch lẫn runtime. Với nhiều mô-đun, việc duy trì một thư mục đầu ra cho mỗi mô-đun giúp module descriptor và package class đi cùng nhau, giảm nhầm lẫn khi phân giải phụ thuộc hoặc đóng gói ứng dụng.
