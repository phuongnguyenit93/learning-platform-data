# Thực hành tổng hợp: đọc tài nguyên trong named module và kiểm thử quyền phản chiếu (JPMS)

## 1. Mục tiêu bài thực hành

Java Platform Module System (JPMS) xuất hiện từ Java 9, giúp đóng gói các thành phần Java thành **named modules** có quan hệ phụ thuộc và quyền truy cập được khai báo trong `module-info.java`. Quy tắc module **vẫn có hiệu lực trên Java 17+ và các JDK hiện đại**.

Bài thực hành này tập trung vào một tình huống rất thực tế: thư viện đặt một file cấu hình trong package nội bộ, ứng dụng bên ngoài muốn đọc file đó; đồng thời ứng dụng dùng reflection để thử gọi một phương thức private. Hai thao tác tưởng như không liên quan nhưng đều phụ thuộc chính sách đóng/mở package của JPMS.

Sau bài này, bạn có thể:

1. Tạo hai named module, biên dịch và chạy trên module path, không cần thư viện bên thứ ba.
2. Đọc tài nguyên qua `Module.getResourceAsStream`, phân biệt quyền đọc từ **bên trong module** và từ **module khác**.
3. Nhận biết vì sao `ClassLoader.getResourceAsStream` có quy tắc hiển thị nghiêm hơn đối với tài nguyên trong package của named module.
4. Phân biệt `requires`, `exports`, `opens ... to ...` và `opens` không điều kiện; kiểm chứng từng trường hợp bằng kết quả chạy thật.
5. Kiểm tra quyền deep reflection bằng `Method.trySetAccessible()` và `Module.isOpen(packageName, otherModule)`, không giả định rằng gọi được `Class.forName` là có quyền đọc thành viên private.
6. Chẩn đoán `null` từ resource API, `InaccessibleObjectException` và lỗi đóng gói tài nguyên; chọn cấu hình tối thiểu đủ dùng, không mở quyền đại trà.

**Định hướng bảo mật:** Không dùng `--add-opens` rộng rãi để che lỗi thiết kế. Khi code bên ngoài cần dữ liệu, giải pháp tốt thường là **API công khai do module sở hữu tài nguyên cung cấp**; chỉ dùng `opens` cho framework hoặc use case thực sự cần truy cập package ở runtime.

## 2. Các tầng quyền JPMS không giống nhau

### 2.1. Hai named module trong bài

~~~text
demo.client  -- requires -->  demo.lib
     |                           |
     | gọi API được exports      | package demo.lib.api
     |                           |
     | thử đọc resource          | package demo.lib.internal
     | thử reflection private    |   - Secret.class
     |                           |   - secret.txt
~~~

- `demo.lib` sở hữu code và tài nguyên trong package `demo.lib.internal`, và cung cấp API hợp lệ trong `demo.lib.api`.
- `demo.client` yêu cầu đọc `demo.lib` bằng chỉ thị `requires demo.lib;`, nhưng quyền **readability** không đồng nghĩa được truy cập mọi package.
- Một package **được export** cho phép code của module khác truy cập các public types và public members theo quy tắc Java. `exports` **không** cho phép deep reflection tới private members.
- Một package **được open** cho phép code của module được cấp quyền dùng cơ chế reflection vượt qua Java language access checks. Với `Module.getResourceAsStream`, `opens` cũng có ý nghĩa đối với tài nguyên không phải `.class` nằm trong package ấy.
- `opens p to demo.client;` chỉ mở cho module `demo.client`; `opens p;` mở không điều kiện cho mọi module. `open module ...` còn mở toàn bộ package ở runtime, thường quá rộng cho một thư viện đóng gói tốt.

### 2.2. Ba API đọc tài nguyên cần phân biệt

| API | Đường dẫn | Đặc điểm cần nhớ |
| --- | --- | --- |
| `Module.getResourceAsStream("a/b/file.txt")` | Đường dẫn resource theo gốc module; dấu `/` đầu nếu có được bỏ qua | Khi file ở package của named module, caller bên ngoài chỉ thấy nếu package **open tới caller module**. Caller trong chính module có thể đọc resource của module mình. |
| `SomeClass.class.getResourceAsStream("file.txt")` | Không bắt đầu bằng `/` thì tương đối với package của `SomeClass`; có `/` đầu thì tuyệt đối theo gốc module/classpath | Trong named module vẫn chịu đóng gói như `Module.getResourceAsStream`; không dùng để vượt `opens`. |
| `ClassLoader.getResourceAsStream("a/b/file.txt")` | Tên tài nguyên tuyệt đối, phân tách bằng `/`; **không** bắt đầu bằng `/` | Với resource không phải `.class` trong package của named module, ClassLoader lookup thông thường đòi package **open không điều kiện** (kể cả khi caller thuộc module sở hữu). `opens ... to ...` chưa đủ. |

Lời gọi có thể trả `null` khi file thiếu, sai đường dẫn, module chưa resolve, class loader không tìm được, hoặc resource bị đóng gói. **Không được suy ra chỉ từ `null` rằng file không tồn tại**, và cũng không suy ra riêng `null` là bị từ chối quyền.

Đặc biệt, API `Module.getResourceAsStream` có ngoại lệ quy tắc đóng gói với tên kết thúc bằng `.class`; đây là quy tắc tra cứu class/resource của JPMS, **không** phải lời mời dùng suffix `.class` để né bảo vệ cho dữ liệu riêng tư.

### 2.3. Kiểm tra phản chiếu có điều kiện

~~~java
Class<?> type = Class.forName("demo.lib.internal.Secret");
java.lang.reflect.Method method = type.getDeclaredMethod("token");
boolean canDeepReflect = method.trySetAccessible();
~~~

Đây là **đoạn mã minh họa**, được đưa vào chương trình đầy đủ ở mục 4. Dù `Class.forName(...)` lấy được đối tượng `Class<?>` và `getDeclaredMethod(...)` tìm được metadata của phương thức private, **việc invoke** vẫn bị kiểm soát. Từ module khác, `trySetAccessible()` trả `false` nếu package không được mở phù hợp. Với `setAccessible(true)`, trường hợp bị từ chối thường ném `java.lang.reflect.InaccessibleObjectException`. `exports` đơn thuần không cấp quyền vượt qua private access.

Không nên nuốt tất cả exception rồi gọi tiếp `invoke`. Hãy kiểm tra rõ kết quả và lựa chọn một đường API công khai khi không được phép reflection.

## 3. Dựng cấu trúc dự án: hai module và hai resource

Tạo các thư mục/tệp sau. Tất cả mã dùng Java 17+ và vẫn phù hợp Java hiện nay.

~~~text
jpms-resource-lab/
└── src/
    ├── demo.lib/
    │   ├── module-info.java
    │   ├── global.txt
    │   └── demo/
    │       └── lib/
    │           ├── api/
    │           │   └── Assets.java
    │           └── internal/
    │               ├── Secret.java
    │               └── secret.txt
    └── demo.client/
        ├── module-info.java
        └── demo/
            └── client/
                └── Main.java
~~~

**Quy ước:** `src/demo.lib` và `src/demo.client` là thư mục source root của mỗi named module. `global.txt` nằm **ở gốc module `demo.lib`**, còn `secret.txt` nằm **trong package `demo.lib.internal`**, là package thực sự tồn tại vì chứa `Secret.java`. Nhờ đó ta kiểm tra chính xác ranh giới đóng gói.

Tạo tệp văn bản với UTF-8 (không cần BOM):

- `src/demo.lib/global.txt` chỉ chứa: `public-resource`
- `src/demo.lib/demo/lib/internal/secret.txt` chỉ chứa: `private-resource`

Không đưa mật khẩu, token thật hay bí mật vận hành vào tài nguyên của một artifact được phân phối. Tên `secret.txt` trong bài chỉ để mô tả kiểm tra quyền truy cập; **JPMS encapsulation không phải cơ chế mã hóa hoặc bảo vệ nội dung khi người khác sở hữu file JAR**.

### 3.1. `src/demo.lib/module-info.java` — cấu hình ban đầu đóng package nội bộ

~~~java
module demo.lib {
    exports demo.lib.api;
}
~~~

Không có `opens demo.lib.internal`, và cũng không `exports demo.lib.internal`. Client chỉ được compile-time access tới `demo.lib.api`.

### 3.2. `src/demo.lib/demo/lib/api/Assets.java` — API đọc từ chính module

~~~java
package demo.lib.api;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public final class Assets {
    private Assets() {}

    public static String readFromInside() throws IOException {
        try (InputStream in = Assets.class.getModule().getResourceAsStream(
                "demo/lib/internal/secret.txt")) {
            if (in == null) {
                throw new IOException("Resource missing");
            }
            return new String(in.readAllBytes(), StandardCharsets.UTF_8).trim();
        }
    }
}
~~~

Lớp `Assets` được `exports` qua package `demo.lib.api`. Khi `Assets` gọi `getResourceAsStream`, **caller thuộc chính `demo.lib`**, vì thế có thể đọc file trong package nội bộ mà **không cần mở package ấy ra bên ngoài**.

Đây là mô hình nên ưu tiên trong ứng dụng thật: module có quyền và trách nhiệm kiểm soát dữ liệu của mình, rồi trả kết quả đã được kiểm tra/biến đổi qua public API. Không cần để client trực tiếp truy cập resource nội bộ.

`try (InputStream in = ...)` giúp đóng tài nguyên kể cả khi có exception. `readAllBytes()` phù hợp file nhỏ; với file lớn, dùng streaming, giới hạn kích thước và encoding rõ ràng.

### 3.3. `src/demo.lib/demo/lib/internal/Secret.java` — lớp cho bài test reflection

~~~java
package demo.lib.internal;

public final class Secret {
    private static String token() {
        return "secret-method";
    }
}
~~~

Class được khai báo `public` nhưng package không export, nên client không thể `import demo.lib.internal.Secret;` như một public API bình thường. Phương thức `token()` còn là `private static`; ngay cả khi export package, nó cũng không tự trở thành phương thức có thể gọi công khai.

### 3.4. `src/demo.client/module-info.java` — client khai báo dependency

~~~java
module demo.client {
    requires demo.lib;
}
~~~

Chỉ thị `requires demo.lib` làm cho module `demo.client` đọc được module `demo.lib`, phục vụ việc import `demo.lib.api.Assets`. Nó **không** cấp phép deep reflection và không làm tài nguyên trong package đóng tự xuất hiện.

### 3.5. `src/demo.client/demo/client/Main.java` — chương trình kiểm thử quyền

~~~java
package demo.client;

import demo.lib.api.Assets;
import java.io.InputStream;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;

public final class Main {
    private static String read(InputStream in) throws Exception {
        if (in == null) {
            return "DENIED_OR_MISSING";
        }
        try (in) {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8).trim();
        }
    }

    public static void main(String[] args) throws Exception {
        Module library = ModuleLayer.boot().findModule("demo.lib").orElseThrow();
        String resource = "demo/lib/internal/secret.txt";

        System.out.println("Inside module: " + Assets.readFromInside());
        System.out.println("From client: "
                + read(library.getResourceAsStream(resource)));
        System.out.println("Root resource: "
                + read(library.getResourceAsStream("global.txt")));
        System.out.println("ClassLoader: "
                + read(ClassLoader.getSystemResourceAsStream(resource)));

        Class<?> secret = Class.forName("demo.lib.internal.Secret");
        Method method = secret.getDeclaredMethod("token");
        boolean allowed = method.trySetAccessible();

        System.out.println("Open to client: "
                + library.isOpen("demo.lib.internal", Main.class.getModule()));
        System.out.println("Private reflection: "
                + (allowed ? method.invoke(null) : "DENIED"));
    }
}
~~~

**Giải thích từng phép thử:**

- `ModuleLayer.boot().findModule("demo.lib")` lấy runtime `Module` của thư viện trong boot layer. Client `requires demo.lib` nên module đích được resolve. Với custom module layer cần lấy từ layer thích hợp thay vì mặc định boot.
- `Assets.readFromInside()` chứng minh việc module **tự đọc** resource của mình là một use case khác với việc client truy cập từ ngoài.
- `library.getResourceAsStream(resource)` thực sự được gọi **từ code của `demo.client`**, nên quyền mở package phải xét theo caller module này.
- `library.getResourceAsStream("global.txt")` lấy resource ở **gốc module**, không thuộc package `demo.lib.internal`; nó vẫn đọc được dù package nội bộ đóng.
- `ClassLoader.getSystemResourceAsStream(resource)` cho thấy lookup chung **không** thay thế hoàn toàn lookup có nhận diện module.
- `Class.forName` và `getDeclaredMethod` tìm được lớp/method để kiểm tra metadata, nhưng `trySetAccessible` mới kiểm tra có được bỏ qua language access checks hay không.
- `method.invoke(null)` hợp lệ khi `token()` là `static`. Chỉ invoke nếu quyền đã được chấp nhận; tránh ném lỗi không cần thiết.

Chuỗi `DENIED_OR_MISSING` cố tình mang hai khả năng để không đánh đồng “không được phép” với “đóng gói thiếu file”. Ở môi trường thực tế, cần kiểm tra cả quyền module, đường dẫn và nội dung artifact (mục 7).

## 4. Biên dịch và chạy bài kiểm thử đầu tiên

Đảm bảo JDK (không chỉ runtime rút gọn) đã cài, các lệnh `java -version` và `javac -version` hoạt động. Chạy từ thư mục gốc `jpms-resource-lab`.

### 4.1. Biên dịch source thành exploded modules

Lệnh sau có thể chạy trong terminal thông thường và trong PowerShell, vì liệt kê cụ thể các tệp Java trên **một dòng**:

~~~bash
javac -encoding UTF-8 --module-source-path src -d mods src/demo.lib/module-info.java src/demo.lib/demo/lib/api/Assets.java src/demo.lib/demo/lib/internal/Secret.java src/demo.client/module-info.java src/demo.client/demo/client/Main.java
~~~

`--module-source-path src` báo rằng các thư mục con của `src` được đặt theo tên module; `-d mods` tạo:

~~~text
mods/
├── demo.lib/
│   ├── module-info.class
│   └── demo/lib/
│       ├── api/Assets.class
│       └── internal/Secret.class
└── demo.client/
    ├── module-info.class
    └── demo/client/Main.class
~~~

**Quan trọng:** `javac` biên dịch tệp Java nhưng **không tự copy** `.txt`. Trước khi chạy, phải đặt cả hai resource vào output đúng vị trí.

Trên **Windows PowerShell**:

~~~powershell
Copy-Item src/demo.lib/demo/lib/internal/secret.txt mods/demo.lib/demo/lib/internal/secret.txt
Copy-Item src/demo.lib/global.txt mods/demo.lib/global.txt
~~~

Trên **Linux/macOS**:

~~~bash
cp src/demo.lib/demo/lib/internal/secret.txt mods/demo.lib/demo/lib/internal/secret.txt
cp src/demo.lib/global.txt mods/demo.lib/global.txt
~~~

Dùng file manager để kiểm tra các tệp sau đã tồn tại:

~~~text
mods/demo.lib/demo/lib/internal/secret.txt
mods/demo.lib/global.txt
~~~

Không dùng đường dẫn tuyệt đối của máy phát triển hoặc `new File("src/...")` trong code production: đường dẫn source không tồn tại khi đóng gói chương trình thành modular JAR. Resource phải được bundle vào artifact, sau đó được mở bằng class/module resource API.

### 4.2. Chạy ở trạng thái package đóng

~~~bash
java --module-path mods -m demo.client/demo.client.Main
~~~

**Stdout chính xác** với JDK 21 và cấu hình ban đầu:

~~~text
Inside module: private-resource
From client: DENIED_OR_MISSING
Root resource: public-resource
ClassLoader: DENIED_OR_MISSING
Open to client: false
Private reflection: DENIED
~~~

Giải thích:

1. `demo.lib.api.Assets` chạy bên trong module sở hữu resource, nên đọc thành công `private-resource`.
2. Code `demo.client.Main` gọi `library.getResourceAsStream(...)` từ **ngoài** package đóng; phương thức trả `null` và helper hiển thị `DENIED_OR_MISSING`.
3. `global.txt` ở gốc module vẫn đọc được, chứng tỏ resource đã được copy và Module API hoạt động.
4. Generic ClassLoader lookup không nhìn thấy resource nằm trong package chưa mở không điều kiện.
5. `library.isOpen("demo.lib.internal", Main.class.getModule())` trả `false`.
6. `Method.trySetAccessible()` trả `false` nên chương trình không được gọi method private `token`.

Lúc này **không có exception bất thường**: việc thiếu quyền đối với package là kết quả chủ đích của descriptor.

## 5. Kiểm thử lần hai: mở package **có điều kiện** cho client

Sửa duy nhất `src/demo.lib/module-info.java` trong **dự án thử nghiệm** thành:

~~~java
module demo.lib {
    exports demo.lib.api;
    opens demo.lib.internal to demo.client;
}
~~~

Câu lệnh `opens ... to ...` cho phép chính `demo.client` truy cập package nội bộ bằng reflection và Module-aware resource lookup. Nó không biến package này thành public API cho các module khác.

Biên dịch lại từ thư mục gốc sau khi **xóa riêng thư mục output `mods` của bài thực hành** hoặc dùng output mới, rồi copy lại hai tệp resource theo đúng hướng dẫn mục 4.1:

~~~bash
javac -encoding UTF-8 --module-source-path src -d mods src/demo.lib/module-info.java src/demo.lib/demo/lib/api/Assets.java src/demo.lib/demo/lib/internal/Secret.java src/demo.client/module-info.java src/demo.client/demo/client/Main.java
java --module-path mods -m demo.client/demo.client.Main
~~~

**Stdout chính xác** sau khi resource đã được copy lại:

~~~text
Inside module: private-resource
From client: private-resource
Root resource: public-resource
ClassLoader: DENIED_OR_MISSING
Open to client: true
Private reflection: secret-method
~~~

Hai thay đổi quan trọng:

- `Module.getResourceAsStream` từ code client bắt đầu thấy resource: package hiện đã **open tới demo.client**.
- `trySetAccessible` thành công nên `method.invoke(null)` trả `secret-method`.

Nhưng `ClassLoader.getSystemResourceAsStream(...)` **vẫn trả `null`** dù mở package có điều kiện! Đây không phải lỗi JDK. API ClassLoader tìm kiếm chung chỉ hiện resource không phải `.class` từ named-module packages khi chúng **opened unconditionally**.

Nếu chỉ cần quyền cho một framework/client cụ thể, nên giữ `opens ... to ...` và dùng API Module-aware hoặc API được module sở hữu công khai, thay vì đổi thành `opens` vô điều kiện chỉ để chiều theo `ClassLoader`.

## 6. Kiểm thử lần ba: mở package không điều kiện

Để hiểu khác biệt, trong **fixture thử nghiệm** thay `module-info.java` thành:

~~~java
module demo.lib {
    exports demo.lib.api;
    opens demo.lib.internal;
}
~~~

Xóa output `mods` cũ, biên dịch lại và copy resource giống các bước trước. Chạy lệnh `java --module-path mods -m demo.client/demo.client.Main`. Kết quả:

~~~text
Inside module: private-resource
From client: private-resource
Root resource: public-resource
ClassLoader: private-resource
Open to client: true
Private reflection: secret-method
~~~

Giờ đây ClassLoader có thể thấy `private-resource` vì package mở không điều kiện. Đổi lại, các module khác cũng có thể dùng reflection với các thành viên nội bộ của package này nếu có tham chiếu phù hợp.

**Bài học kiến trúc:** Kết quả “chạy được” chưa chắc là cấu hình đúng. Với code nội bộ, ưu tiên `exports` một facade API nhỏ hoặc `opens p to m` cho đúng consumer; không mở package cho mọi module chỉ để thuận tiện. Chỉ dùng `opens p;` hoặc `open module` nếu có lý do rõ ràng, phạm vi thích hợp và kiểm thử tương ứng.

## 7. Bảng so sánh đã thực nghiệm

Kết quả ba lần chạy với **hai named module** và hai tài nguyên được copy đúng vào output:

| Phép thử | Không `opens` | `opens demo.lib.internal to demo.client` | `opens demo.lib.internal` |
| --- | --- | --- | --- |
| `Assets.readFromInside()` | `private-resource` | `private-resource` | `private-resource` |
| Client dùng `Module.getResourceAsStream` trong package nội bộ | `DENIED_OR_MISSING` | `private-resource` | `private-resource` |
| Client dùng `Module.getResourceAsStream("global.txt")` | `public-resource` | `public-resource` | `public-resource` |
| Client dùng `ClassLoader.getSystemResourceAsStream` trong package nội bộ | `DENIED_OR_MISSING` | `DENIED_OR_MISSING` | `private-resource` |
| `library.isOpen("demo.lib.internal", clientModule)` | `false` | `true` | `true` |
| `Method.trySetAccessible()` và `invoke(null)` | `DENIED` | `secret-method` | `secret-method` |

Bảng thể hiện quy tắc hiển thị của `Module` và `ClassLoader` đối với **resource không có đuôi `.class`**. Kết quả được kiểm chứng trên JDK 21; từng API cũng được tài liệu Java SE hiện đại mô tả tương tự.

Muốn tự động hóa, có thể cho CI chạy cả ba biến thể trên module path, so sánh stdout hoặc chuyển từng dòng thành assert. Không nên viết một bài test “mở package” bằng cách lén đưa mọi class lên classpath, vì ở **unnamed module**, quy tắc đóng gói thay đổi và không kiểm tra được JPMS như dự định.

## 8. `exports` và `opens` giải quyết các vấn đề khác nhau

| Chỉ thị trong `module-info.java` | Compile-time public API | Deep reflection vào private member từ client | Resource trong package qua `Module.getResourceAsStream` từ client |
| --- | --- | --- | --- |
| Không `exports`, không `opens` | Không | Không | Không |
| `exports demo.lib.internal;` | Có (public types/members) | Không | Không |
| `exports demo.lib.internal to demo.client;` | Có cho `demo.client` | Không | Không |
| `opens demo.lib.internal to demo.client;` | Không mở public API theo nghĩa `exports` | Có cho `demo.client` | Có cho `demo.client` |
| `opens demo.lib.internal;` | Không thay việc export public API ở compile time | Có cho mọi module | Có cho mọi module |

Cần nhớ:

- `requires demo.lib;` tạo *readability*: client có thể đọc module nhưng không tự có quyền đến package không export.
- `exports p;` cho phép dùng public surface của package ở biên giới module; không làm private field/method khả dụng cho deep reflection.
- `opens p to target;` cấp quyền reflective access/runtime resource cho package p với một module đích, không khiến source code client được `import` class chưa export.
- `opens p;` rộng hơn `opens p to target;`. Trên module descriptor, lựa chọn này ảnh hưởng cả **người được thực hiện deep reflection** lẫn một số phương thức lookup resource.
- Nếu đã có public API ổn định, hãy cho client gọi method API thay vì điều chỉnh descriptor để truy cập thẳng implementation.

**Tình huống hay gặp:** Framework JSON/DI/ORM dùng reflection để truy cập constructor và field private. Khi thư viện/framework ở một named module riêng, việc khai báo `opens model.package to framework.module;` có thể đúng hơn `exports model.package;`. Tên module thật phải dựa trên artifact/framework đang dùng; không tự đoán hoặc thêm `ALL-UNNAMED` khi caller đã có tên module.

## 9. Kiểm thử phản chiếu an toàn: `trySetAccessible` và `setAccessible`

### 9.1. Sự khác nhau

Hai phương thức của `AccessibleObject` có thể dùng để yêu cầu bỏ qua Java language access checks:

~~~java
// Đoạn minh họa nằm trong code có Method method.
if (method.trySetAccessible()) {
    Object value = method.invoke(null); // Private static method của bài thực hành.
    System.out.println(value);
} else {
    System.out.println("No access to private method");
}
~~~

`trySetAccessible()` trả `false` nếu không bật được quyền, giúp code nhánh hóa rõ ràng thay vì dựa vào exception để điều khiển logic. Với `setAccessible(true)`:

~~~java
// Đoạn minh họa chẩn đoán trên một Method chưa được cấp quyền.
try {
    method.setAccessible(true);
    System.out.println(method.invoke(null));
} catch (java.lang.reflect.InaccessibleObjectException denied) {
    System.out.println("Module does not open the package to caller");
}
~~~

Ở biến thể đóng package của bài thực hành, lệnh `setAccessible(true)` gặp `InaccessibleObjectException`. Không nên bắt mọi `RuntimeException` rồi giả vờ như phép reflection đã thành công.

**Lưu ý:** `getDeclaredMethod` có thể ném `NoSuchMethodException` khi nhầm tên/chữ ký; `Class.forName` có thể ném `ClassNotFoundException` nếu class chưa có trong module/path; `Method.invoke` có thể ném `InvocationTargetException` khi chính method được gọi phát sinh lỗi. Những lỗi này **khác** với việc package không `opens`. Chương trình mẫu dùng `trySetAccessible` để tách rõ case “không có quyền” trước khi gọi.

### 9.2. Dùng `Module.isOpen` và `isExported` để hỗ trợ chẩn đoán

~~~java
// Đoạn minh họa: library là Module demo.lib; client là Module demo.client.
boolean openToClient = library.isOpen("demo.lib.internal", client);
boolean exportedToClient = library.isExported("demo.lib.internal", client);
~~~

`isOpen` trả mức mở package theo thông tin runtime; `isExported` phản ánh quyền export thích hợp. Không suy ra một kết luận dựa vào **chỉ một** boolean: Java có thể chạy với module path khác, dynamic layer khác hoặc các command-line options điều chỉnh quyền.

Chúng cũng **không** chứng minh file `secret.txt` đã tồn tại hay method có đúng tên. Vì vậy hãy kết hợp quyền, file layout, resource lookup và reflection call thật.

### 9.3. Command-line `--add-opens` chỉ là đường chẩn đoán/thích nghi có kiểm soát

Trên cấu hình đóng package của bài thực hành, có thể **thử tạm**:

~~~bash
java --add-opens demo.lib/demo.lib.internal=demo.client --module-path mods -m demo.client/demo.client.Main
~~~

Lệnh này mở package của `demo.lib` cho riêng `demo.client` ở lần chạy đó, mà không đổi `module-info.java`. Kết quả mong đợi đối với Module lookup và reflection tương tự bản `opens ... to demo.client;`; nhưng generic ClassLoader lookup vẫn cần unconditional opens theo contract.

**Không xem `--add-opens` là giải pháp mặc định cho production.** Nếu thuộc sở hữu code, sửa descriptor/API cho đúng. Với thư viện ngoài không kiểm soát được, chỉ cấp quyền tối thiểu, lưu lại lý do và kiểm thử khi nâng phiên bản. Không dùng `--add-opens ...=ALL-UNNAMED` nếu caller thực tế là named module và không có lý do rõ ràng.

## 10. `Class.getResourceAsStream` và lỗi đường dẫn

### 10.1. Relative path khác absolute path

Giả sử resource `secret.txt` nằm cạnh `Secret.class` trong package `demo.lib.internal`:

~~~java
// Đoạn minh họa bên trong code thuộc demo.lib, nơi có Secret.class.
Secret.class.getResourceAsStream("secret.txt");
Secret.class.getResourceAsStream("/demo/lib/internal/secret.txt");
~~~

Hai lời gọi đều có thể trỏ về resource đó vì:

- `"secret.txt"` được hiểu là đường dẫn tương đối so với package chứa `Secret`.
- `"/demo/lib/internal/secret.txt"` được hiểu là tên tuyệt đối, bỏ dấu `/` đầu trước khi tìm resource trong module.

Còn `Module.getResourceAsStream("demo/lib/internal/secret.txt")` dùng tên từ gốc module, không tự thêm package. `ClassLoader.getResourceAsStream("demo/lib/internal/secret.txt")` cũng dùng đường dẫn tuyệt đối nhưng có quy tắc encapsulation chung chặt hơn.

**Đừng thay hết các API bằng nhau chỉ vì cú pháp giống nhau**: cái gì đang đại diện caller module, resource package có mở không, và tên đường dẫn được chuẩn hóa thế nào đều có ý nghĩa.

### 10.2. Resource nằm trong package vs resource ở gốc module

Kết quả `global.txt` của bài thực hành là minh họa một file **ở gốc module**, không nằm trong một Java package. Ngược lại, `demo/lib/internal/secret.txt` được xem là tài nguyên thuộc `demo.lib.internal` vì module thực sự có package ấy. Đây là khác biệt quan trọng khi dự đoán `Module.getResourceAsStream` có chịu kiểm tra `opens` hay không.

Không nên đưa file cấu hình mật mã hoặc dữ liệu cần giữ kín ra gốc module chỉ để “đọc được”; người sở hữu artifact vẫn có thể trích xuất file từ package/JAR. Nếu cần bảo vệ bí mật, dùng secret manager/kho lưu trữ an toàn và chính sách phân quyền ở tầng hệ thống.

### 10.3. Không dựa vào đường dẫn thư mục của IDE

Code sau có thể “chạy tốt trong IDE” nhưng không dùng đúng cơ chế resource đóng gói:

~~~java
// SAI khi giả định mọi môi trường production đều có thư mục source:
java.nio.file.Files.readString(
        java.nio.file.Path.of("src/demo.lib/demo/lib/internal/secret.txt"));
~~~

Khi đưa vào modular JAR, đường dẫn `src/...` biến mất. Hãy để build tool đặt resource đúng vào output/JAR và dùng `Module`/`Class` resource API. Đối với file bên ngoài cần người vận hành thay đổi ở runtime, cố ý dùng một đường dẫn cấu hình ngoài artifact; đó là **use case khác** với bundled resource.

## 11. Đóng gói modular JAR và kiểm thử sau build

Hai resource cần xuất hiện trong artifact của `demo.lib`. Trong ví dụ build thủ công, sau bước biên dịch và copy, có thể tạo modular JAR:

~~~bash
jar --create --file demo.lib.jar -C mods/demo.lib .
jar --describe-module --file demo.lib.jar
~~~

`jar --describe-module` cho phép kiểm tra descriptor được đóng gói. Việc xác thực resource nên được thực hiện bằng cách liệt kê entry trong JAR hoặc chạy test tích hợp, vì descriptor một mình không thể chứng minh file `secret.txt` đã vào artifact.

Trên Linux/macOS:

~~~bash
jar --list --file demo.lib.jar
~~~

Trên Windows PowerShell dùng cùng lệnh `jar --list --file demo.lib.jar`. Danh sách kết quả cần chứa ít nhất các mục:

~~~text
module-info.class
global.txt
demo/lib/api/Assets.class
demo/lib/internal/Secret.class
demo/lib/internal/secret.txt
~~~

Thứ tự entry không quan trọng. Sau khi đổi descriptor `opens`, phải đóng gói lại JAR và chạy với module path mới; đừng chỉ thay source `module-info.java` mà quên compile.

Trong Maven/Gradle, thông thường `src/main/resources` được copy vào artifact theo cấu hình plugin/build; vị trí đường dẫn **bên trong JAR** mới là yếu tố để `getResourceAsStream` hoạt động. Kiểm tra bản build thật thay vì giả định đường dẫn source trở thành đường dẫn runtime.

## 12. Hướng tiếp cận tốt hơn khi module cần kiểm soát dữ liệu

Thay vì buộc mọi client biết đường dẫn resource nội bộ và mở package, module thư viện có thể cung cấp một facade hẹp:

~~~java
package demo.lib.api;

import java.io.IOException;

public final class PublicSettings {
    private PublicSettings() {}

    public static String publicLabel() throws IOException {
        // Chỉ xuất bản dữ liệu đã qua kiểm tra, không trả toàn bộ raw config.
        return Assets.readFromInside();
    }
}
~~~

Đây là **đoạn mở rộng minh họa**, không thuộc năm tệp `.java` tối thiểu của bài test. Nếu muốn biên dịch, lưu trong `src/demo.lib/demo/lib/api/PublicSettings.java` và thêm vào build. Không dùng nguyên xi API này để tiết lộ bí mật; ví dụ chỉ cho thấy public facade có thể kiểm soát thứ được trả.

Các nguyên tắc thiết kế có thể tái sử dụng:

1. Module sở hữu tài nguyên có thể tự đọc, xác thực và trả dữ liệu đã lọc qua API được `exports`.
2. Khi client cần service động, cân nhắc dùng `ServiceLoader` và khai báo `uses/provides` đúng cách, thay vì tự phản chiếu vào implementation private.
3. Chỉ `opens` package khi framework/runtime thực sự cần deep reflection; dùng qualified opens khi module đích có tên.
4. Không đưa credential hoặc secret lâu dài vào resource được phân phối trong JAR. Encapsulation là ranh giới API, không phải cơ chế chống người đọc trực tiếp file artifact.
5. Viết integration test chạy **trên module path thật** để phát hiện sự khác biệt giữa IDE/classpath và môi trường triển khai.
6. Đừng sửa `module-info.java` chỉ để cho một lookup method tiện dụng hơn; trước tiên cân nhắc dùng `Module.getResourceAsStream` đúng caller hoặc API do module quản lý.

## 13. Chẩn đoán khi kiểm thử thất bại

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| `getResourceAsStream` trả `null` ở cả trong `Assets` | File chưa copy vào output, sai tên hoặc chữ hoa/thường | Kiểm tra file `mods/demo.lib/demo/lib/internal/secret.txt` và tên chính xác trong JAR. |
| `Assets` đọc được nhưng client không đọc được | Package không mở cho module client | Kiểm tra `module-info.java` và `Module.isOpen(package, clientModule)`. |
| `Module` lookup được, ClassLoader lookup vẫn `null` | Package chỉ `opens ... to demo.client` | Đó là hành vi đúng: ClassLoader cần unconditional opens để tìm resource nằm trong named-module package. |
| `trySetAccessible() == false` | Package không mở tới caller module, hoặc điều kiện Java access khác không đạt | Kiểm tra `Module.isOpen`, caller module thực tế và method được phản chiếu. |
| `setAccessible(true)` ném `InaccessibleObjectException` | JPMS không cho phép suppress access checks | Dùng API công khai hoặc qualified `opens` khi hợp lý; tránh bỏ kiểm soát. |
| `Class.forName` ném `ClassNotFoundException` | Module chưa resolve, sai tên class, thiếu class trong output | Kiểm tra module path, dependency, tên package và entry class trong JAR. |
| `NoSuchMethodException` | Sai method name/parameter types | Dùng đúng chữ ký trong `getDeclaredMethod(name, types...)`. |
| `IllegalAccessException` khi gọi `invoke` | Chưa có quyền truy cập method phù hợp | Kiểm tra kết quả `trySetAccessible` trước khi invoke. |
| `InvocationTargetException` | Method được gọi thực sự ném exception | Kiểm tra `getCause()`, không chẩn đoán nhầm thành module không mở. |
| `java.lang.module.FindException`/`ResolutionException` | Lỗi tìm hoặc giải module trên module path | Kiểm tra tên, artifact, version, split packages và quan hệ `requires`. |
| Test pass trên classpath nhưng fail trên module path | Classpath code ở unnamed module có quy tắc khác | Chạy đúng dạng `java --module-path ... -m ...`, không trộn scope. |
| Output đổi descriptor nhưng kết quả cũ | Build output/JAR chưa cập nhật, command chạy nhầm artifact | Xóa riêng thư mục output test và build lại; kiểm tra `jar --describe-module`. |

**Quy trình điều tra đúng thứ tự:**

1. Xác nhận đang chạy named module: `Main.class.getModule().isNamed() == true`.
2. In `module.getName()` và `ModuleLayer` thích hợp; chắc chắn `demo.lib` đã được resolve.
3. Kiểm tra tệp thực sự có trong output hoặc JAR theo **đường dẫn tương đối chuẩn**.
4. Nếu code bên trong module đọc được nhưng module khác không đọc được, so sánh `isOpen(package, callerModule)` và vị trí resource.
5. Nếu reflection không thành công, phân biệt `ClassNotFoundException`, `NoSuchMethodException`, `trySetAccessible()==false`, `InaccessibleObjectException` và lỗi phát ra bên trong method.
6. Chỉ sau khi phân định nguyên nhân mới quyết định thay descriptor hay thay API đọc resource.

Không xử lý thiếu quyền bằng cách bắt chung `Throwable`/`Exception` rồi trả giá trị cấu hình mặc định có thể nguy hiểm. Khi file bắt buộc đối với tính đúng đắn/bảo mật, báo lỗi rõ ràng và fail-fast.

## 14. Kiểm thử âm và dương nên có trong CI

Một bài kiểm thử quyền truy cập tốt cần ít nhất:

- **Negative – đóng package:** resource bên trong được module thư viện đọc; caller bên ngoài nhận `null`; `trySetAccessible() == false`.
- **Positive – qualified opens:** client được đọc bằng `Module.getResourceAsStream` và dùng private reflection khi được mở; generic ClassLoader lookup vẫn không thấy resource trong package.
- **Positive – unconditional opens:** generic ClassLoader lookup thấy resource; điều này đồng thời cảnh báo scope mở quá rộng.
- **Resource ở gốc module:** `global.txt` vẫn có thể đọc được trong cả ba biến thể.
- **Negative – thiếu đóng gói resource:** cố ý bỏ `secret.txt` khỏi output/JAR để bảo đảm test phát hiện thiếu file thay vì nhầm với quyền.
- **Negative – sai đường dẫn/case:** đặc biệt kiểm tra trên hệ thống file phân biệt hoa thường, vì path trong JAR phân biệt chính xác.
- **Negative – reflection sai tên:** phân biệt `NoSuchMethodException` với thiếu quyền.
- **Build thực tế:** chạy sau khi build modular JAR bằng công cụ dự án, không chỉ trong IDE.

Một test tốt **không nên mở quyền bằng `--add-opens` trong toàn bộ pipeline** nếu mục tiêu là xác minh descriptor; tùy chọn ấy có thể khiến test negative pass nhầm. Hãy giữ config module/path của test sát môi trường production.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Có `requires demo.lib;` rồi, tại sao `demo.client` vẫn không đọc được `secret.txt` nằm trong `demo.lib.internal`?

Vì `requires` chỉ thiết lập module readability. Resource thuộc package đóng của một named module còn chịu JPMS resource encapsulation; caller bên ngoài cần quyền `opens` phù hợp hoặc phải dùng API do thư viện cung cấp.

**Câu 2.** Vì sao `Assets.readFromInside()` đọc được `secret.txt` ngay cả khi `demo.lib.internal` chưa `opens`?

Vì lời gọi từ `Assets` thuộc chính module sở hữu resource. Quy tắc mở package áp dụng khi caller nằm trong module khác; package private không ngăn module sở hữu tự đọc.

**Câu 3.** Vì sao `opens demo.lib.internal to demo.client;` làm `Module.getResourceAsStream` thành công nhưng `ClassLoader.getSystemResourceAsStream` vẫn trả `null`?

Vì ClassLoader lookup với resource không phải `.class` trong named-module package đòi package **open không điều kiện**; qualified opens chỉ cho phép những module đích đã khai báo.

**Câu 4.** Tại sao `Class.forName("demo.lib.internal.Secret")` chạy được nhưng `trySetAccessible()` lại trả `false`?

Vì việc tìm được metadata của một class không tương đương quyền suppress Java language access checks hay invoke private method qua ranh giới module.

**Câu 5.** Câu lệnh `exports demo.lib.internal;` có làm `Method.trySetAccessible()` cho `private static token()` thành công không?

Không chỉ nhờ `exports`. Export chủ yếu phục vụ public API; muốn private deep reflection từ module khác cần `opens` thích hợp hoặc điều kiện truy cập khác được API cho phép.

**Câu 6.** Mỗi lần sửa `module-info.java`, vì sao phải build lại và copy resource vào đúng output?

Vì JVM đọc compiled module descriptor, còn `javac` không tự đặt mọi tệp resource vào `-d`. Chạy lại binary cũ sẽ khiến kết quả không phản ánh source mới.

**Câu 7.** Có nên đặt API key của production vào `secret.txt` rồi dựa vào package không `opens` để bảo mật không?

Không. JPMS encapsulation không ngăn người sở hữu JAR trích xuất nội dung; phải dùng cơ chế quản lý bí mật và bảo vệ artifact/hệ thống riêng.

**Câu 8.** Nếu thật sự chỉ muốn client đọc một giá trị cấu hình đã được duyệt, nên chọn cách nào?

Ưu tiên một exported public facade trong module thư viện, thực hiện đọc và lọc nội bộ. Chỉ cấp `opens` trực tiếp nếu đó là contract có chủ đích, ví dụ framework reflection cần truy cập package.

## 16. Tóm tắt quyết định

~~~text
Bạn cần đọc resource của named module?
    |
    +-- Code ở cùng module?
    |      +-- Dùng Class/Module resource API và đóng stream.
    |
    +-- Code ở module khác?
           |
           +-- Có API công khai do module sở hữu cung cấp?
           |      +-- Có: dùng API, không mở package vô cớ.
           |
           +-- Cần trực tiếp đọc resource trong package?
                  +-- Dùng Module.getResourceAsStream.
                  +-- Kiểm tra package mở tới caller module.
                  +-- Nếu không có quyền: fail-fast / sửa descriptor đúng scope.

Bạn cần reflection vào member private?
    |
    +-- Có API public được export thay thế?
    |      +-- Có: ưu tiên API public.
    |
    +-- Bắt buộc deep reflection qua module boundary?
           +-- Kiểm tra isOpen / trySetAccessible.
           +-- Mở package có điều kiện cho đúng module nếu hợp lý.
           +-- Không dùng Class.forName như phép thử cấp quyền.
~~~

**Kết luận:** Quy tắc cốt lõi của JPMS là tách biệt rõ **đọc module**, **truy cập public API**, **đọc resource ở runtime** và **deep reflection**. Một tài nguyên có thể tồn tại nhưng không thể nhìn thấy từ module khác; một class có thể được tìm thấy nhưng method private của nó không thể invoke. Bài test hai module và ba biến thể `opens` giúp phát hiện đúng ranh giới trước khi triển khai vào hệ thống thật.

## 17. Tài liệu chuẩn hiện hành

- [Oracle Java SE 26 — `Module.getResourceAsStream`, `isOpen` và `isExported`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Module.html)
- [Oracle Java SE 26 — `Class.getResourceAsStream` và quy tắc path](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html)
- [Oracle Java SE 26 — `ClassLoader.getResourceAsStream` trong named modules](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassLoader.html)
- [Oracle Java SE 26 — `AccessibleObject.trySetAccessible` và `setAccessible`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Oracle Java SE 26 — `InaccessibleObjectException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html)
- [Oracle Java SE 26 — `Method.invoke` và `getDeclaredMethod`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Method.html)
- [Oracle Java SE 26 — Java launcher `--module-path`, `--add-opens`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [Java Language Specification — `7.7 Module Declarations`](https://docs.oracle.com/javase/specs/jls/se26/html/jls-7.html#jls-7.7)