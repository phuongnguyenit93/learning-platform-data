# Tài nguyên trong named module: quy tắc đóng gói và `opens`

Khi chuyển ứng dụng Java từ classpath sang **named module (JPMS, Java 9+)**, lập trình viên có thể gặp tình huống: file `.properties` hoặc `.txt` **đã nằm trong JAR**, một class của module đọc được, nhưng `ClassLoader.getResourceAsStream()` lại trả về `null`. Đây không nhất thiết là lỗi đường dẫn hay đóng gói: **resource trong package của named module có thể bị đóng gói (encapsulated)**. Khả năng đọc còn phụ thuộc **API đang dùng**, **module của caller** và **package có được `opens` hay không**.

Bài học giải thích việc định danh tài nguyên, cấu trúc module/JAR, cách tìm bằng `Class`, `Module`, `ClassLoader`, ý nghĩa của `exports` / `opens` / `open module` / `--add-opens`, rồi thực hành bằng một project Java 17+ có thể biên dịch và chạy được.

## 1. Resource và named module là gì?

**Resource** là dữ liệu được ứng dụng nạp lúc runtime: văn bản, cấu hình, template, ảnh, schema, bản dịch, metadata… Chúng thường nằm cạnh `.class` trong thư mục output, trong JAR hoặc trong module image. Resource thông thường **không phải một Java class** và `javac` không tự chép mọi file dữ liệu đi theo mã nguồn.

**Named module** là module Java có tên xác định, thường khai báo bằng `module-info.java` và được đưa vào module path hoặc một module layer phù hợp. Một module có thể chứa:

```text
demo.resources (named module)
├── module-info.class
├── demo/
│   ├── app/
│   │   └── Main.class
│   └── assets/
│       ├── Anchor.class
│       └── note.txt
└── META-INF/
    └── build-info.txt
```

Ví dụ trên có class `demo.assets.Anchor`, vì vậy **`demo.assets` là một package thực sự thuộc module**. File `demo/assets/note.txt` có resource name gắn với package đó. Ngược lại, `META-INF/build-info.txt` nằm ngoài một Java package hợp lệ (`META-INF` không phải tên package Java), nên không bị encapsulation theo cùng cách.

Không nên đánh đồng ba khái niệm:

- **Resource path**: đường dẫn với dấu `/`, ví dụ `demo/assets/note.txt`.
- **Package name**: tên có dấu `.`, ví dụ `demo.assets`.
- **Module name**: ví dụ `demo.resources`, xác định không gian module và một phần chính sách đóng gói.

Class loader có thể định nghĩa các class thuộc nhiều module, nhưng điều đó **không có nghĩa tất cả resource trong các module ấy công khai như trên classpath cũ**.

## 2. Hai loại đóng gói cần tách biệt: vật lý và truy cập

Một file có thể rơi vào bốn trạng thái sau:

| File có trong module output/JAR? | Tên resource đúng? | Package được mở phù hợp? | Có thể đọc bằng API đang dùng? |
|---|---|---|---|
| Không | Bất kỳ | Bất kỳ | Không |
| Có | Không | Có | Không, vì lookup sai tên |
| Có | Có | Không | **Có thể bị trả `null`** do encapsulation |
| Có | Có | Có | Có thể đọc, nếu loader có thể tìm resource và không có lỗi I/O khác |

Vì vậy **`null` không chứng minh file không tồn tại**. Cần xác minh đồng thời: nội dung artifact, tên resource, package/module và chính xác API/caller nào đang yêu cầu.

### Quy tắc resource package theo `Module.getResourceAsStream`

Với một resource như `a/b/c/config.properties`, tên package được suy ra từ phần đứng trước dấu `/` cuối cùng, tức `a.b.c`.

- Nếu `a.b.c` **là một package thuộc named module**, resource `config.properties` bị encapsulated. Caller ở module khác chỉ đọc được qua `Module.getResourceAsStream` nếu package mở tới module của caller.
- Nếu tên tài nguyên **kết thúc bằng `.class`**, đặc tả không áp dụng resource encapsulation này cho resource đó.
- Nếu tên resource không chỉ tới một package thuộc module, resource **không bị encapsulated** theo quy tắc ấy. Ví dụ `META-INF/MANIFEST.MF` có thành phần `META-INF` không phải package Java.
- Khả năng truy cập vẫn cần file thực sự hiện diện và tìm thấy; quy tắc mở package không làm xuất hiện resource bị thiếu.

**Đặc biệt:** một thư mục `config/` chứa vài file không tự biến thành package chỉ vì nó tồn tại trong JAR. Trái lại, nếu `demo.assets` có class thuộc module thì `demo/assets/note.txt` rõ ràng là resource trong package `demo.assets`.

## 3. Ba API đọc resource có quy tắc khác nhau

### 3.1. `Class.getResourceAsStream` và `Class.getResource`

```java
InputStream relative =
        Anchor.class.getResourceAsStream("note.txt");

InputStream absolute =
        Anchor.class.getResourceAsStream("/demo/assets/note.txt");
```

Đây là **mảnh minh họa**, với `Anchor` ở package `demo.assets` và có file `note.txt`.

Khi dùng `Class`:

1. Nếu tên **không bắt đầu bằng `/`**, Java ghép với package của class đại diện: `"note.txt"` thành `demo/assets/note.txt`.
2. Nếu tên bắt đầu bằng `/`, tên được hiểu theo đường dẫn tuyệt đối tính từ gốc resource space: `"/demo/assets/note.txt"` được chuẩn hóa thành `demo/assets/note.txt`.
3. Nếu class thuộc **named module**, lookup được hướng tới chính module đó và tuân theo encapsulation của `Module.getResourceAsStream`. Caller trong **cùng module** có thể truy cập resource trong package của chính module (module mở package cho chính nó); caller ở module khác cần package được mở thích hợp.

`Class.getResource` trả `URL` hoặc `null`; `Class.getResourceAsStream` trả `InputStream` hoặc `null`. Có resource mà không đọc được còn có thể phát sinh lỗi I/O khi mở/đọc stream.

### 3.2. `Module.getResourceAsStream(String)`

```java
Module module = Anchor.class.getModule();
try (InputStream in =
        module.getResourceAsStream("demo/assets/note.txt")) {
    // Xử lý in; có thể null.
}
```

API này chọn **module cụ thể** bằng đối tượng `Module` và dùng resource name theo dạng `/`, có thể bỏ dấu `/` đầu. Quan trọng nhất: **kiểm tra quyền mở package đối với module của caller**.

Trong cùng named module, code của module có thể đọc resource của chính module mà không phải public hóa package ra mọi nơi. Nếu code ở module khác gọi API này, package chứa resource cần mở tới **module caller** (mở công khai hoặc qualified opens tương ứng).

`Module.getResourceAsStream` khai báo `throws IOException`. Vì vậy nên dùng `try-with-resources` và xử lý cả trường hợp `null` lẫn lỗi I/O thực sự.

### 3.3. `ClassLoader.getResourceAsStream` / `getResource`

```java
ClassLoader loader = Anchor.class.getClassLoader();
InputStream in =
        loader.getResourceAsStream("demo/assets/note.txt");
```

Đây là mảnh minh họa; phải tự đóng stream nếu khác `null`.

**Điểm rất quan trọng của named module:** theo JDK 17, với resource **không kết thúc bằng `.class`** nằm trong package của một named module, `ClassLoader.getResource` / `getResources` / `getResourceAsStream` chỉ tìm được resource khi package được **opened unconditionally** — nghĩa là mở vô điều kiện cho tất cả module.

Điều này đúng **ngay cả khi caller của `ClassLoader.getResourceAsStream` nằm trong cùng module**. API `ClassLoader` không dùng ngữ cảnh module caller giống `Module.getResourceAsStream`.

Với resource `demo/assets/note.txt` trong module `demo.resources`:

- Module không khai báo `opens demo.assets;`: `Anchor.class.getResourceAsStream("note.txt")` khi gọi từ cùng module có thể đọc được, nhưng `loader.getResourceAsStream("demo/assets/note.txt")` trả `null`.
- Khi thêm `opens demo.assets;` vào `module-info.java`, cả hai đường đọc đều có thể tìm thấy resource.
- Nếu chỉ dùng `opens demo.assets to some.consumer;`, điều đó **không biến package thành opened unconditionally**, nên `ClassLoader.getResourceAsStream` vẫn không phải lựa chọn tin cậy cho resource này.

### Bảng so sánh

| API | Kiểu tên resource | Scope tìm kiếm | Quy tắc `opens` với resource thường trong package của named module |
|---|---|---|---|
| `Anchor.class.getResourceAsStream("note.txt")` | Tương đối package của Anchor | Module chứa Anchor | Package cần open tới caller module; tự gọi từ cùng module được |
| `Anchor.class.getResourceAsStream("/demo/assets/note.txt")` | Tuyệt đối từ gốc resource | Module chứa Anchor | Như trên |
| `Anchor.class.getModule().getResourceAsStream("demo/assets/note.txt")` | Đường dẫn trong module | Module được chỉ định | Package cần open tới caller module; cùng module được |
| `Anchor.class.getClassLoader().getResourceAsStream("demo/assets/note.txt")` | Đường dẫn với `/`, không tự thêm package | Qua class loader | Package cần **open unconditionally**, trừ ngoại lệ như `.class` |
| `ClassLoader.getSystemResourceAsStream("demo/assets/note.txt")` | Đường dẫn với `/` | Qua system loader | Cũng chịu quy tắc named-module resources của `ClassLoader` |

Không có API nào “bỏ qua mọi ranh giới module”. Các API có *scope* và quy tắc truy cập khác nhau.

## 4. `exports`, `opens`, `open module` khác nhau

Xem module descriptor:

```java
module demo.resources {
    exports demo.app;
    opens demo.assets;
}
```

Đây là **ví dụ khai báo**, không phải file riêng ngoài `module-info.java`.

| Khai báo | Mục đích chính | Có đủ cho `ClassLoader.getResourceAsStream` đọc `demo/assets/note.txt`? |
|---|---|---|
| Không khai báo gì cho `demo.assets` | Đóng package với module khác | Không |
| `exports demo.assets;` | Cho module đọc phù hợp truy cập public types/members | **Không** — exports không đồng nghĩa opens |
| `exports demo.assets to consumer;` | Xuất public API có chọn lọc | Không |
| `opens demo.assets;` | Mở package vô điều kiện để deep reflection và resource access | **Có**, nếu resource tồn tại |
| `opens demo.assets to consumer;` | Mở package cho consumer đã chỉ định | **Không**, vì không unconditional |
| `open module demo.resources { ... }` | Mở mọi package trong module | Có với các resource package hiện diện, nhưng phạm vi quyền rộng |

**`exports` và `opens` không thay thế nhau**:

- `exports` chủ yếu phục vụ truy cập các **public Java types và members** cho module đọc phù hợp.
- `opens` mở package cho khả năng reflective access sâu theo quy tắc JPMS và **ảnh hưởng trực tiếp đến việc tìm resource**.
- `opens ... to m1, m2;` chỉ mở cho danh sách module cụ thể.
- `open module ...` mở toàn bộ package trong module; không nên chọn chỉ để sửa một resource bị `null` nếu chỉ cần mở package nhỏ hơn.

Trong cùng module, mã Java thường dùng trực tiếp package không `exports` và truy cập resource của mình qua `Class`/`Module`. **Không cần xuất public API chỉ để đọc file cấu hình nội bộ**.

### `--add-opens` có tương đương `opens p;` không?

Không hoàn toàn. Ví dụ:

```bash
java --add-opens demo.resources/demo.assets=ALL-UNNAMED \
     --module-path mods -m demo.resources/demo.app.Main
```

Tùy chọn này mở `demo.assets` **có mục tiêu** tới các unnamed modules. Nó không giống khai báo mở vô điều kiện `opens demo.assets;`. Vì thế đừng mặc định `ClassLoader.getResourceAsStream` sẽ tìm được mọi resource của package đó sau `--add-opens`. Muốn truy cập trong chính module, dùng `Class`/`Module` thường chính xác hơn; nếu cần classloader-based lookup rộng, cân nhắc `opens` vô điều kiện và đánh giá hệ quả encapsulation.

**Không dùng `--add-exports` thay `--add-opens`** để giải quyết encapsulation của non-`.class` resources.

## 5. Thí nghiệm Java 17+: file có thật nhưng `ClassLoader` trả `null`

Ví dụ sau chạy ở chế độ **named module** với Java 17+. Nó được tổ chức đủ để phân biệt **lỗi thiếu resource** và **resource bị encapsulated**.

### 5.1. Cấu trúc project

```text
project/
├── src/
│   ├── module-info.java
│   └── demo/
│       ├── app/
│       │   └── Main.java
│       └── assets/
│           └── Anchor.java
├── resources/
│   ├── demo/
│   │   └── assets/
│   │       └── note.txt
│   └── META-INF/
│       └── build-info.txt
├── mods/                    (sinh khi biên dịch)
└── dist/                    (sinh khi tạo modular JAR)
```

Có hai package được định nghĩa bởi code: `demo.app` và `demo.assets`. Resource `demo/assets/note.txt` nằm trong package `demo.assets`, trong khi `META-INF/build-info.txt` không thuộc một package Java hợp lệ.

### 5.2. Tệp `src/module-info.java`

```java
module demo.resources {
}
```

Ban đầu **không `exports` và không `opens`** để kiểm chứng quy tắc mặc định. `Main` và `Anchor` cùng thuộc module nên mã trong module có thể tham chiếu trực tiếp `Anchor`.

### 5.3. Tệp `src/demo/assets/Anchor.java`

```java
package demo.assets;

public final class Anchor {
    private Anchor() {
    }
}
```

Class này đóng vai trò **mốc package** khi gọi `Anchor.class.getResourceAsStream("note.txt")`. Ta không cần tạo instance Anchor.

### 5.4. Tệp `src/demo/app/Main.java`

```java
package demo.app;

import demo.assets.Anchor;
import java.io.InputStream;

public final class Main {
    private static boolean exists(InputStream in) throws Exception {
        if (in == null) {
            return false;
        }
        try (in) {
            return in.read() != -1;
        }
    }

    public static void main(String[] args) throws Exception {
        Module module = Anchor.class.getModule();
        ClassLoader loader = Anchor.class.getClassLoader();
        String name = "demo/assets/note.txt";

        System.out.println("named module: " + module.isNamed());
        System.out.println("Module API: "
                + exists(module.getResourceAsStream(name)));
        System.out.println("Class relative: "
                + exists(Anchor.class.getResourceAsStream("note.txt")));
        System.out.println("Class absolute: "
                + exists(Anchor.class.getResourceAsStream("/" + name)));
        System.out.println("ClassLoader API: "
                + exists(loader.getResourceAsStream(name)));
        System.out.println("META-INF resource: "
                + exists(loader.getResourceAsStream(
                        "META-INF/build-info.txt")));
    }
}
```

Hàm `exists` dùng `try-with-resources` để đóng stream và kiểm tra tài nguyên có ít nhất một byte. Các file dữ liệu trong ví dụ sẽ được tạo không rỗng, do đó kết quả `true` không bị lẫn với resource rỗng. Trong ứng dụng thực tế, nên đặt tên `read...` nếu cần đọc/parse toàn bộ file, thay vì chỉ dùng phép thử này.

### 5.5. File dữ liệu

`resources/demo/assets/note.txt`:

```text
hello
```

`resources/META-INF/build-info.txt`:

```text
build=test
```

Hai file trên là dữ liệu thông thường, **không** phải source Java.

### 5.6. Biên dịch và copy resource

Các lệnh sau dùng Bash trên Linux/macOS, chạy ở thư mục `project`:

```bash
mkdir -p mods/demo.resources/demo/assets
mkdir -p mods/demo.resources/META-INF
mkdir -p dist

javac -d mods/demo.resources \
    src/module-info.java \
    src/demo/app/Main.java \
    src/demo/assets/Anchor.java

cp resources/demo/assets/note.txt \
   mods/demo.resources/demo/assets/note.txt

cp resources/META-INF/build-info.txt \
   mods/demo.resources/META-INF/build-info.txt
```

**Vì sao cần `cp`?** `javac` chỉ biên dịch các file `.java` đã chỉ định; nó không tự lấy tất cả `.txt` từ `resources/`. Muốn module thực sự chứa file cấu hình, phải copy vào output theo đúng resource path hoặc cấu hình build tool để thực hiện việc đó.

Lệnh chạy:

```bash
java --module-path mods -m demo.resources/demo.app.Main
```

**Stdout chính xác khi module chưa khai báo `opens`:**

```text
named module: true
Module API: true
Class relative: true
Class absolute: true
ClassLoader API: false
META-INF resource: true
```

### 5.7. Vì sao kết quả trông ngược trực giác?

- `module.isNamed()` trả `true`: code đang ở named module.
- `Module API: true`: caller `demo.app.Main` thuộc **chính module chứa resource**, nên `Module.getResourceAsStream` tìm được `demo/assets/note.txt`.
- `Class relative/absolute: true`: `Anchor.class` định vị resource trong cùng module; cú pháp relative và absolute cùng trỏ đúng file.
- `ClassLoader API: false`: file vẫn tồn tại; khác biệt là package `demo.assets` **chưa opened unconditionally** nên classloader-based resource lookup không thấy non-`.class` resource trong package đó.
- `META-INF resource: true`: path không thuộc Java package trong module, do vậy quy tắc package encapsulation không chặn nó.

**Đây không phải lỗi class loader bị hỏng.** Cùng một project, cùng runtime, cùng resource name tuyệt đối nhưng API có encapsulation rule khác nhau.

### 5.8. Thay `module-info.java` bằng `opens demo.assets;`

Sửa **chỉ tệp `src/module-info.java`** trong project ví dụ thành:

```java
module demo.resources {
    opens demo.assets;
}
```

Biên dịch lại module descriptor và class:

```bash
javac -d mods/demo.resources \
    src/module-info.java \
    src/demo/app/Main.java \
    src/demo/assets/Anchor.java

java --module-path mods -m demo.resources/demo.app.Main
```

File `.txt` đã được copy vào thư mục output và không bị `javac` xóa trong các lệnh trên.

**Stdout lúc này:**

```text
named module: true
Module API: true
Class relative: true
Class absolute: true
ClassLoader API: true
META-INF resource: true
```

Chỉ cần thêm **`opens demo.assets;`** là kết quả `ClassLoader API` đổi từ `false` thành `true`. Đây là minh chứng trực tiếp cho quy tắc **unconditional opens**.

### 5.9. Đóng gói thành modular JAR và chạy tiếp

Sau khi biên dịch bản có `opens`, đóng gói **cùng output đã có resource**:

```bash
jar --create --file dist/demo.resources.jar \
    -C mods/demo.resources .

jar --list --file dist/demo.resources.jar

java --module-path dist -m demo.resources/demo.app.Main
```

Output của lệnh `jar --list` có các entry quan trọng như:

```text
module-info.class
demo/app/Main.class
demo/assets/Anchor.class
demo/assets/note.txt
META-INF/build-info.txt
```

Danh sách thực tế có thể kèm `META-INF/MANIFEST.MF` hoặc metadata khác, tùy công cụ JAR. Điều cần kiểm tra là **hai resource thật sự hiện diện**, đúng đường dẫn, và `module-info.class` đã được đóng gói.

Với bản `opens`, chạy từ `dist/demo.resources.jar` cho **cùng sáu dòng stdout** của phần 5.8. Đây là bài kiểm tra đóng gói: nếu chạy từ thư mục `mods` thành công nhưng từ JAR thất bại, cần tìm vấn đề ở quá trình copy/resource packaging thay vì mặc định đổ lỗi cho `opens`.

## 6. Khi đọc resource từ module khác

Giả sử có named module `demo.consumer`, cần đọc `demo/assets/note.txt` nằm ở module `demo.resources`. Với API:

```java
Module provider = Anchor.class.getModule();
try (InputStream in =
        provider.getResourceAsStream("demo/assets/note.txt")) {
    // Caller đang chạy trong demo.consumer.
}
```

Đây là **mảnh minh họa**, chỉ biên dịch khi consumer có quyền tham chiếu tới `Anchor` hoặc bằng một cách phù hợp lấy được đối tượng `Module` provider.

Nếu `demo.resources` chưa mở `demo.assets` cho consumer, `getResourceAsStream` có thể trả `null` dù resource tồn tại. Có các cách mở:

```java
module demo.resources {
    opens demo.assets to demo.consumer;
}
```

Khai báo này mở **có chọn lọc** cho `demo.consumer`; chỉ cần nêu đúng target module. Nếu consumer trực tiếp import public class `Anchor`, cần xét **`exports demo.assets to demo.consumer;`** và module readability riêng, vì **`opens` không mặc nhiên là lời khai báo public compile-time API cho consumer**.

Một phương án giảm kết nối giữa consumer và package nội bộ là provider module đưa ra **public resource-reading API** ở package được `exports`. Provider code tự dùng `Class`/`Module` để đọc resource nội bộ, rồi trả dữ liệu theo hợp đồng API. Cách đó thường an toàn hơn việc mở một package nội bộ chỉ để consumer tìm file.

**Lưu ý quan trọng:** `opens demo.assets to demo.consumer;` đủ cho `Module.getResourceAsStream` được consumer gọi nếu các điều kiện khác hợp lệ; nhưng **không đủ** cho quy tắc classloader-based lookup đòi hỏi mở **vô điều kiện**.

## 7. Các trường hợp resource không nằm trong package

Không phải mọi resource trong named module đều bị encapsulated. Ví dụ:

```text
META-INF/services/com.example.Service
META-INF/build-info.txt
config/application.properties
demo/assets/note.txt
```

Nhìn vào nơi chứa các Java packages thực tế:

- `META-INF` không phải Java package hợp lệ; resource ở đó không bị package encapsulation theo `Module.getResourceAsStream`.
- `config/application.properties` chỉ bị xem như resource trong package `config` nếu `config` thực sự là một package của named module. Nếu không có package tương ứng trong module, resource không bị encapsulated bởi quy tắc package.
- `demo/assets/note.txt` nằm trong package `demo.assets` khi module có class `demo.assets.Anchor`; khi ấy quy tắc `opens` áp dụng.
- Nếu resource path kết thúc bằng `.class`, đặc tả có ngoại lệ với resource encapsulation. **Không đồng nghĩa mọi `.class` đều công khai để thực thi như API Java**, vì class visibility, module exports và linking là các cơ chế khác.

Đừng xem việc chuyển file vào `META-INF` là thủ thuật để vượt quyền một cách tùy tiện. Hãy chọn vị trí dựa trên mục đích dữ liệu và hợp đồng build/module; resource public và resource private nên được thiết kế có chủ đích.

### `META-INF/services` và `ServiceLoader`

Với ứng dụng classpath truyền thống, service provider configuration thường nằm ở `META-INF/services/...`. Trong **named modules**, `ServiceLoader` còn dùng các khai báo trong module descriptor:

```java
module demo.provider {
    provides com.example.spi.Handler
        with com.example.provider.HandlerImpl;
}
```

Đây là **ví dụ cú pháp minh họa**; nó cần các kiểu và module phù hợp mới biên dịch. Không được thay thế cơ chế `provides`/`uses` của named module bằng giả định rằng đọc `META-INF/services` thủ công là tương đương service loading qua JPMS.

## 8. `open module` và công cụ CLI: nên áp dụng ở mức nào?

Một module có thể khai báo:

```java
open module demo.resources {
}
```

Mọi package của module được mở vô điều kiện. Resource lookup qua `ClassLoader` có thể nhìn thấy các resource thường trong các package tương ứng nếu chúng hiện diện.

Nhưng mở cả module thường **rộng hơn cần thiết**: code khác cũng có thể có thêm khả năng deep reflection vào các package ấy. Nếu chỉ một package chứa resource cần được công khai, ưu tiên:

```java
module demo.resources {
    opens demo.assets;
}
```

Nếu mục tiêu chỉ là **đọc dữ liệu nội bộ**, lại có lựa chọn bảo toàn encapsulation tốt hơn: **đừng mở**; dùng `Anchor.class.getResourceAsStream(...)` hoặc `Anchor.class.getModule().getResourceAsStream(...)` từ code **cùng module**.

### Cân nhắc với thư viện/framework

Framework có thể dùng `ClassLoader.getResource(...)` hoặc thread context class loader để tìm tài nguyên theo path. Khi chuyển framework từ classpath sang named module, mã ứng dụng dùng `Class` đọc được không đảm bảo framework cũng đọc được.

Các hướng xử lý phải dựa trên API thật sự của framework:

1. Nếu framework hỗ trợ truyền `InputStream`, `URL` hoặc cấu hình đã đọc sẵn, provider có thể tự đọc bằng `Class`/`Module` rồi truyền cho framework.
2. Nếu framework buộc dùng `ClassLoader.getResource` và package chứa tài nguyên phải công khai, cân nhắc `opens p;` với ý thức rằng phạm vi mở vô điều kiện.
3. Nếu framework tải service providers, annotation/metadata hoặc module layers, xem cơ chế JPMS chuyên dụng của framework; đừng sửa `exports`/`opens` theo thử-sai mà không hiểu caller.
4. Nếu cần resource chia sẻ độc lập module package, thiết kế vị trí/đường dẫn resource ở phạm vi công khai hợp lệ ngay từ đầu.

## 9. Phân biệt lỗi đóng gói, tên đường dẫn và module encapsulation

Một thứ tự chẩn đoán thực tế:

**Bước 1: In module và loader**

```java
Class<?> anchor = Anchor.class;

System.out.println(anchor.getModule().getName());
System.out.println(anchor.getModule().isNamed());
System.out.println(anchor.getClassLoader());
```

Đây là mảnh code khi `Anchor` tồn tại trong scope. Trên classpath thông thường, `getModule().isNamed()` có thể là `false` (unnamed module), nên không nên áp dụng bừa quy tắc của named module.

**Bước 2: Xác nhận nội dung vật lý**

```bash
jar --list --file dist/demo.resources.jar
```

Tìm chính xác `demo/assets/note.txt`, `module-info.class` và resource khác. `javac` không copy file data tự động; build tool có thể bị cấu hình bỏ qua `resources/`.

**Bước 3: Xác nhận resource name**

```java
Anchor.class.getResourceAsStream("note.txt");
Anchor.class.getResourceAsStream("/demo/assets/note.txt");
Anchor.class.getClassLoader()
    .getResourceAsStream("demo/assets/note.txt");
```

Hai cách đầu (dưới `Class`) tương đương trong ví dụ vì Anchor ở `demo.assets`. `ClassLoader` cần đường dẫn từ gốc, không tự ghép package và không dùng dấu `/` đầu như quy ước relative của `Class`.

**Bước 4: Xác nhận package và trạng thái mở**

```java
Module module = Anchor.class.getModule();
String pkg = "demo.assets";

System.out.println(module.getPackages().contains(pkg));
System.out.println(module.isOpen(pkg));
System.out.println(module.isOpen(pkg, module));
```

Với module chưa khai báo `opens` trong thí nghiệm, các kết quả là:

```text
true
false
true
```

Giải thích: package tồn tại; **không opened unconditionally**; nhưng package của module được xem là open đối với **chính module đó**. Đây chính là khác biệt mà `ClassLoader` và `Module` resource APIs biểu hiện.

**Bước 5: Chọn API đúng và chỉ mở đúng phạm vi cần thiết**

Nếu file dùng nội bộ module, ưu tiên API module/class. Nếu bên ngoài cần resource, quyết định rõ module nào được phép đọc và framework sử dụng API nào. Chỉ khi thực sự cần lookup dựa trên class loader cho mọi bên mới cân nhắc unconditional opens.

## 10. Những lỗi hiểu sai phổ biến

1. **“File đã nằm trong JAR thì `ClassLoader.getResourceAsStream` phải đọc được.”** Sai với resource trong package của named module chưa mở vô điều kiện.
2. **“`exports p;` là đủ cho tất cả resource trong p.”** Sai: exports chủ yếu điều khiển truy cập public Java API, không thay thế opens cho resource encapsulation.
3. **“Tôi đang gọi `ClassLoader` từ cùng module nên sẽ luôn đọc được.”** Sai: classloader-based lookup yêu cầu package opens unconditional cho non-`.class` resources trong named module.
4. **“`opens p to m;` tương đương `opens p;`.”** Sai: một cái mở có chọn lọc, một cái mở vô điều kiện.
5. **“`Class.getResourceAsStream("note.txt")` tìm từ gốc JAR.”** Sai: khi không có dấu `/` đầu, nó ghép với package của class.
6. **“`Module.getResourceAsStream` luôn tìm toàn bộ module graph.”** Sai: API đọc resource **trong module object đã chọn**.
7. **“Resource dưới `META-INF` mặc nhiên là package trong module.”** Sai: `META-INF` không phải Java package, nên không bị encapsulated theo cùng quy tắc.
8. **“`javac` tự đóng gói mọi file `resources`.”** Sai: phải copy hoặc cấu hình build tool.
9. **“Đọc được resource nghĩa là class trong package ấy được public/exported.”** Sai: resource access và truy cập Java types là hai cơ chế khác nhau.
10. **“`--add-opens ...=ALL-UNNAMED` mở package vô điều kiện cho mọi API.”** Sai: nó mở có mục tiêu cho unnamed modules.
11. **“Một named module luôn nằm trong file JAR.”** Sai: module có thể tồn tại dưới dạng exploded module directory, modular JAR hoặc runtime image.
12. **“Một resource `.class` không bị encapsulated nên tôi có thể dùng mọi class private/internal.”** Sai: ngoại lệ resource lookup không bỏ qua linkage, Java access hay JPMS exports.
13. **“Trả `null` luôn là lỗi Java module system.”** Sai: tên sai, file thiếu, đóng gói sai, class loader khác hoặc resource path mismatch cũng có thể trả `null`.

## 11. Checklist build & packaging resource cho named module

- [ ] Có `module-info.java` và chạy đúng `--module-path ... -m module/class` khi cần thử named module.
- [ ] `javac` đã tạo `module-info.class` và tất cả class đúng package path.
- [ ] Resource data được copy vào **module output** đúng tên và đường dẫn.
- [ ] Modular JAR / exploded module thực sự chứa file sau build.
- [ ] Tên truyền cho `Class.getResourceAsStream` relative/absolute đúng quy tắc dấu `/`.
- [ ] Tên truyền cho `Module.getResourceAsStream` dùng đường dẫn trong module.
- [ ] Tên truyền cho `ClassLoader.getResourceAsStream` là path với `/`, không dựa vào package tương đối.
- [ ] Đã biết tên package suy ra từ resource và package đó có thuộc module không.
- [ ] Đã xác định caller ở cùng module hay module khác.
- [ ] Chỉ dùng `exports` cho nhu cầu public Java API; dùng `opens` khi cần mở package.
- [ ] Chỉ dùng **unconditional opens** nếu API dựa trên `ClassLoader` thực sự cần resource của package.
- [ ] Đã kiểm tra với artifact cuối (JAR/module image), không chỉ thư mục output của IDE.
- [ ] Đã đóng `InputStream` bằng `try-with-resources` để không rò rỉ tài nguyên.

## 12. Tự kiểm tra

**Câu 1.** `demo.assets` là package thuộc named module `demo.resources`. File `demo/assets/note.txt` tồn tại. Module không khai báo `opens`. Tại sao code trong chính module đọc được bằng `Anchor.class.getResourceAsStream("note.txt")` nhưng `Anchor.class.getClassLoader().getResourceAsStream("demo/assets/note.txt")` trả `null`?

**Đáp án:** `Class` dùng lookup theo module và xét quyền mở cho module caller (chính module có quyền đọc dữ liệu của mình). `ClassLoader` chỉ hiển thị resource thường trong package của named module nếu package được opened **unconditionally**.

**Câu 2.** Thêm `exports demo.assets;` có chắc sửa kết quả `ClassLoader` trong câu 1 không?

**Đáp án:** Không. Exports không tương đương opens; cần `opens demo.assets;` khi dùng classloader-based lookup, hoặc dùng API khác đúng phạm vi.

**Câu 3.** `opens demo.assets to demo.consumer;` có cho consumer dùng `Module.getResourceAsStream` không? Có bảo đảm `ClassLoader.getResourceAsStream` hoạt động không?

**Đáp án:** Nó có thể cho code trong module `demo.consumer` đọc resource bằng Module API (giả định resource tìm thấy và các điều kiện khác hợp lệ). Nhưng không mở **vô điều kiện**, nên không đủ điều kiện bắt buộc của classloader-based lookup cho non-`.class` resource trong package này.

**Câu 4.** Tại sao `META-INF/build-info.txt` được `ClassLoader` đọc trong ví dụ mà `demo/assets/note.txt` không được?

**Đáp án:** `META-INF` không phải tên Java package hợp lệ; resource ở đó không bị package encapsulation. `demo.assets` là package thực của module và chưa opened unconditionally.

**Câu 5.** Nếu chạy được ở `mods/demo.resources` nhưng đóng gói JAR xong không thấy resource, bước đầu kiểm tra gì?

**Đáp án:** Dùng `jar --list --file ...` để xác nhận resource được chép vào modular JAR đúng path; kiểm tra build resource copying trước khi thay `opens`.

## 13. Mô hình ghi nhớ

```text
Muốn đọc một resource trong named module:
                 |
                 v
File có trong module output/JAR và đúng path?
          /                 \
       Không                 Có
         |                    |
  Sửa packaging        Resource có nằm trong
                       package thật của module?
                           /        \
                        Không        Có
                          |           |
                 Không encapsulated  Caller/API nào?
                 theo package rule    |
                                     +-- Class/Module:
                                     |     same module hoặc
                                     |     package open tới caller
                                     |
                                     +-- ClassLoader:
                                           package phải
                                           opened unconditionally
                                           (với non-.class resource)
```

**Tóm tắt ba nguyên tắc:**

1. **Đúng artifact và resource name trước:** chưa copy file hay gọi nhầm path thì mọi `opens` đều vô ích.
2. **Named module có resource encapsulation:** `Class`/`Module` cân nhắc caller module; `ClassLoader` yêu cầu opens vô điều kiện đối với resource thường trong package của named module.
3. **Chọn mức mở nhỏ nhất đáp ứng API:** nội bộ module nên đọc bằng `Class`/`Module`; xuất public API dùng `exports`; mở package cho reflection/resource khi thật sự cần bằng `opens` phù hợp.

### Tài liệu chuẩn

- [Java SE 17 — Module.getResourceAsStream: module resource encapsulation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html#getResourceAsStream(java.lang.String))
- [Java SE 17 — Class.getResourceAsStream: đường dẫn tương đối và named module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getResourceAsStream(java.lang.String))
- [Java SE 17 — ClassLoader.getResource / getResourceAsStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#getResourceAsStream(java.lang.String))
- [Java Language Specification, `7.7.2: Module Declarations, exports và opens](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.2)
