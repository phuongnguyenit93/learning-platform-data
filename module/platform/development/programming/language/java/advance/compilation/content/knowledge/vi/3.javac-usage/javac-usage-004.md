# Dùng `javac -d` để tổ chức thư mục đầu ra

Khi biên dịch một chương trình Java, bạn thường muốn giữ mã nguồn `.java` riêng với bytecode `.class`. Tùy chọn **`-d` (destination directory)** của `javac` giải quyết việc này: nó chọn **thư mục gốc chứa các class file được tạo ra** và đặt từng class file vào cây thư mục tương ứng với **tên package** (và tên module nếu đang biên dịch nhiều module).

Thói quen đáng dùng là viết mã trong `src/`, đưa bytecode vào `build/classes/` hoặc `out/`, rồi khi chạy chỉ rõ **đúng thư mục gốc bytecode**. Bài này tập trung vào cách `-d` tổ chức file, cách biên dịch/chạy và các lỗi dễ mắc liên quan đến đường dẫn.

## 1. Cú pháp và ý nghĩa chính xác

```text
javac -d <thu-muc-dich> <danh-sach-tep-java>
```

Ví dụ:

```sh
javac --release 17 -encoding UTF-8 -d out src/demo/Main.java
```

Ý nghĩa từng phần:

- `javac`: trình biên dịch Java trong JDK.
- `--release 17`: dùng ngôn ngữ, class-file target và API nền tảng tương ứng Java 17 (khi JDK đang dùng hỗ trợ mục tiêu này).
- `-encoding UTF-8`: đọc mã nguồn với UTF-8.
- **`-d out`**: đặt **gốc output** tại thư mục `out`, tính tương đối so với thư mục làm việc hiện tại.
- `src/demo/Main.java`: tệp mã nguồn được biên dịch; `-d` **không thay thế** việc truyền nguồn vào `javac`.

Với JDK 17 trở lên theo tài liệu `javac` hiện hành, `javac` có thể tạo thư mục đích và các thư mục package còn thiếu. Các hướng dẫn JDK rất cũ có thể yêu cầu tạo sẵn thư mục gốc; nếu viết script cần hỗ trợ nhiều phiên bản JDK, tạo sẵn đích là cách làm dễ hiểu và ổn định.

`-d` chỉ xác định **nơi ghi class file**. Nó không đổi tên package, không tự chạy `main`, không tự đóng gói JAR, không tải thư viện và không tự xóa file cũ khi biên dịch lại.

### Khi không chỉ định `-d`

Với cách biên dịch nguồn truyền thống (không biên dịch nhiều module), `javac` mặc định đặt class file **cạnh tệp nguồn**. Chẳng hạn, nếu tệp nguồn là `src/demo/Main.java`, `javac src/demo/Main.java` thường tạo `src/demo/Main.class`. Việc này dễ làm cây `src/` lẫn lộn cả source và build output.

| Cách gọi | Nơi xuất class file của `package demo; class Main` |
| --- | --- |
| `javac src/demo/Main.java` | `src/demo/Main.class` |
| `javac -d out src/demo/Main.java` | `out/demo/Main.class` |
| `javac -d build/classes src/demo/Main.java` | `build/classes/demo/Main.class` |

Các đường dẫn trong bảng giả định nguồn là tệp hợp lệ và việc biên dịch thành công. Dấu `/` thể hiện cấu trúc thư mục theo cách đọc chung; Windows dùng dấu `\` khi hiển thị đường dẫn hệ thống.

## 2. Quy tắc quan trọng: thư mục theo package, không theo vị trí `.java`

Giả sử mã nguồn khai báo:

```java
package com.acme.tools;

public class Greeter {
}
```

Nếu biên dịch tệp `Greeter.java` đó với `-d build/classes`, đường dẫn đầu ra tương ứng là:

```text
build/
└── classes/
    └── com/
        └── acme/
            └── tools/
                └── Greeter.class
```

Công thức cho một kiểu top-level thông thường:

```text
<class-output-root>/<package-thay-dấu-chấm-bằng-thư-mục>/<TenLop>.class
```

Vì vậy:

- **`-d build/classes` chọn gốc**, không có nghĩa tất cả `.class` được đặt phẳng ngay trong thư mục này.
- **`package com.acme.tools;` tạo nhánh `com/acme/tools/`**. `javac` dựa vào khai báo package của kiểu, không dựa vào tên thư mục `src` hay đường dẫn tệp nguồn để quyết định package.
- Nếu lớp **không khai báo package** (unnamed/default package), class file được đặt ngay dưới gốc output, ví dụ `build/classes/Plain.class`.
- Một tệp nguồn có thể tạo **nhiều** class file: lớp top-level phụ, lớp lồng nhau, anonymous class hoặc cấu trúc ngôn ngữ khác đều có thể tạo thêm file. Không nên áp quy tắc “mỗi `.java` đúng một `.class`”.

Trong dự án thực tế, hãy sắp xếp nguồn theo package để dễ tìm, ví dụ `src/com/acme/tools/Greeter.java`. Đó là quy ước tổ chức nguồn hữu ích; **`-d` điều khiển output**, không phải công cụ sửa cấu trúc source.

## 3. Ví dụ hoàn chỉnh Java 17: nguồn ở `src/`, bytecode ở `build/classes/`

Tạo dự án với **hai package** tách biệt:

```text
project/
└── src/
    └── com/
        └── example/
            ├── util/
            │   └── Greeting.java
            └── app/
                └── Main.java
```

Nội dung `src/com/example/util/Greeting.java`:

```java
package com.example.util;

public final class Greeting {
    private Greeting() {
    }

    public static String message() {
        return "Hello from -d";
    }
}
```

Nội dung `src/com/example/app/Main.java`:

```java
package com.example.app;

import com.example.util.Greeting;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
```

Từ thư mục `project`, sử dụng JDK 17+ và biên dịch cả hai tệp trong cùng một lần gọi:

```sh
javac --release 17 -encoding UTF-8 -d build/classes src/com/example/util/Greeting.java src/com/example/app/Main.java
```

Nếu thành công, lệnh `javac` thường không in gì ra terminal. Cây đầu ra:

```text
project/
├── src/
│   └── com/
│       └── example/
│           ├── util/Greeting.java
│           └── app/Main.java
└── build/
    └── classes/
        └── com/
            └── example/
                ├── util/Greeting.class
                └── app/Main.class
```

Lúc chạy, dùng **gốc output `build/classes`** làm runtime classpath và tên lớp main đầy đủ:

```sh
java -cp build/classes com.example.app.Main
```

**Stdout chính xác:**

```text
Hello from -d
```

Tại sao câu lệnh chạy đúng?

1. `-d build/classes` yêu cầu compiler đặt class file dưới thư mục `build/classes`.
2. `package com.example.app;` biến tên đầy đủ thành `com.example.app.Main`; class file nằm tại `build/classes/com/example/app/Main.class`.
3. `java -cp build/classes ...` đưa **thư mục chứa gốc của cây package** vào classpath; JVM ánh xạ tên `com.example.app.Main` tới file theo đường dẫn tương ứng.
4. `Greeting` nằm trong package khác, nhưng cũng nằm dưới **cùng gốc output**, nên runtime tìm được thông qua classpath đó.

Lệnh **sai** thường thấy:

```sh
java -cp build/classes/com/example/app Main
```

Trong ví dụ trên, `Main` **không thuộc default package**. Chỉ định một thư mục quá sâu rồi gọi bằng tên ngắn `Main` sẽ không khớp tên lớp đã biên dịch. Câu lệnh đúng là `java -cp build/classes com.example.app.Main`.

> **Lưu ý:** `-d` có thể nhận đường dẫn tương đối như `out` hoặc đường dẫn tuyệt đối. Đường dẫn tương đối được tính từ **working directory hiện tại của tiến trình `javac`**; chạy lệnh từ thư mục khác có thể đặt output ở nơi khác. Nếu đường dẫn có khoảng trắng, dùng dấu nháy theo shell, ví dụ `-d "build/java classes"`.

## 4. Quan hệ giữa `-d`, `-cp` và `-sourcepath`

Ba tùy chọn dễ bị nhầm có trách nhiệm khác nhau:

| Tùy chọn | Chức năng | Ví dụ |
| --- | --- | --- |
| `-d` | Chỉ định **nơi ghi** class files của lần biên dịch | `-d build/classes` |
| `-cp` / `--class-path` | Chỉ định **nơi tìm** các lớp/thư viện cho compilation; `java -cp` chọn runtime classpath | `-cp build/classes` |
| `-sourcepath` / `--source-path` | Chỉ định đường dẫn tìm **mã nguồn phụ thuộc** để compiler có thể biên dịch khi cần | `-sourcepath src` |

Chúng không tương đương nhau. Cụ thể, trong dự án Java **không biên dịch theo named module**, thư mục `-d` **không tự động được thêm vào classpath của chính `javac`**. Vì thế, khi bạn chia biên dịch thành nhiều lượt, phải chủ động cho compiler biết cách tìm các `.class` đã tạo.

### Ví dụ biên dịch hai lượt, sử dụng lại output cũ

Từ **đúng hai tệp `Greeting.java` và `Main.java` ở mục 3**, có thể thực hiện:

```sh
javac --release 17 -encoding UTF-8 -d build/classes src/com/example/util/Greeting.java
javac --release 17 -encoding UTF-8 -cp build/classes -d build/classes src/com/example/app/Main.java
java -cp build/classes com.example.app.Main
```

Stdout của lệnh cuối:

```text
Hello from -d
```

Lần một sinh `Greeting.class`. Lần hai **đọc `Greeting.class` từ `-cp build/classes`** rồi xuất `Main.class` vào cùng thư mục qua `-d build/classes`. Nếu bỏ `-cp build/classes`, lượt hai có thể gặp lỗi kiểu `package com.example.util does not exist` hoặc `cannot find symbol`, tùy cách bố trí nguồn, classpath và các thiết lập khác.

Khi dùng thư viện JAR ngoài, thêm chúng vào **classpath biên dịch** và đảm bảo **classpath runtime** cũng có các phụ thuộc cần thiết. Nếu cần nhiều phần tử classpath thì ký tự phân cách là `;` trên Windows và `:` trên Linux/macOS. Để giảm lỗi khi học `-d`, ví dụ chính không dùng thư viện ngoài.

### `-d` không quyết định namespace của lớp

Chạy:

```sh
javap -classpath build/classes com.example.app.Main
```

`javap` đọc bytecode ở classpath và giúp kiểm tra lớp đã được biên dịch. Thông tin package của `Main` vẫn là `com.example.app`, vì đó là khai báo trong mã nguồn. Đổi `-d build/classes` thành `-d out` chỉ đổi **vị trí lưu output**; không đổi tên đầy đủ của lớp.

## 5. Tại sao nên dùng một thư mục output riêng?

**Dễ tách nhiệm vụ:** `src/` chứa mã nguồn con người sửa; `build/classes/` chỉ chứa bytecode được sinh từ quá trình biên dịch. Bạn có thể phát hiện file sinh ra, xem log và đóng gói rõ ràng hơn.

**Đường dẫn chạy ổn định:** dùng một classpath root rõ ràng, chẳng hạn `java -cp build/classes com.example.app.Main`, thay vì phải suy đoán từng thư mục chứa `.class`.

**Dễ gói JAR:** sau khi biên dịch thành công ví dụ ở mục 3, có thể đóng gói tất cả class files dưới gốc output:

```sh
jar --create --file build/app.jar -C build/classes .
java -cp build/app.jar com.example.app.Main
```

Stdout của lệnh chạy vẫn là:

```text
Hello from -d
```

Ở đây, `jar -C build/classes .` đưa nội dung **bên trong** cây `build/classes` vào gốc JAR, nên JAR có entry `com/example/app/Main.class` và `com/example/util/Greeting.class`. Lệnh `jar` là bước **đóng gói riêng**, không phải một hiệu ứng của `javac -d`. Ví dụ không ghi `Main-Class` vào manifest nên chạy bằng `java -cp build/app.jar ...`; không tự suy ra rằng `java -jar build/app.jar` sẽ hoạt động.

**Có thể kiểm tra đầu ra:** dùng lệnh liệt kê file của hệ điều hành, `jar --list --file build/app.jar` để xem JAR, hoặc `javap -classpath build/classes com.example.app.Main` để xem lớp. Đây là cách kiểm chứng nơi xuất thay vì suy đoán từ terminal không in lỗi.

**Dễ giao cho build tool:** Maven và Gradle thường quản lý riêng thư mục class output, generated sources, resources và artifact đóng gói. `-d` chính là khái niệm tương ứng ở mức lệnh `javac`, dù chi tiết tên đường dẫn do build tool quyết định.

## 6. Các trường hợp đầu ra cần biết

### 6.1. Lớp không có `package`

Tệp `src/Plain.java`:

```java
public class Plain {
    public static void main(String[] args) {
        System.out.println("Plain class");
    }
}
```

Biên dịch và chạy:

```sh
javac --release 17 -d out src/Plain.java
java -cp out Plain
```

Đầu ra class là `out/Plain.class`, và stdout là:

```text
Plain class
```

Vì lớp không khai báo package, không có nhánh `out/src/` hay `out/Plain/`. Đây là trường hợp đơn giản để kiểm tra bạn có đang truyền **đúng tên lớp** vào `java` hay không. Trong ứng dụng lớn, package tường minh thường dễ quản lý hơn default package.

### 6.2. Lớp lồng nhau làm xuất hiện nhiều `.class`

Với một tệp có dạng:

```java
package sample;

public class Container {
    public static class Nested {
    }
}
```

Nếu tệp tên `Container.java` được biên dịch với `-d out`, những class file điển hình là:

```text
out/
└── sample/
    ├── Container.class
    └── Container$Nested.class
```

Dấu `$` là một phần của tên file nhị phân cho kiểu lồng nhau ở ví dụ này. `-d` vẫn chỉ chọn gốc `out`; compiler quyết định số lượng và tên class file phù hợp với những kiểu trong nguồn. Các ví dụ lambda, local/anonymous class hoặc các cấu trúc khác có thể tạo file phụ theo cách không nên hard-code giả định.

### 6.3. Biên dịch named modules

Khi biên dịch nhiều **named modules** trong một lần gọi có cấu hình module source path phù hợp, thư mục `-d` có thể được tổ chức thêm một tầng **tên module** trước cây package:

```text
out/
├── com.example.alpha/
│   ├── module-info.class
│   └── com/example/alpha/...
└── com.example.beta/
    ├── module-info.class
    └── com/example/beta/...
```

Đây là **sơ đồ cấu trúc minh họa** cho output nhiều module, không phải kết quả của các lệnh classpath ví dụ trước. Đừng áp đặt cây nhiều module lên mọi lệnh `javac -d`; với bài Java thông thường không có `module-info.java`, ta sẽ thấy cây package như các mục 2–3.

Khi **biên dịch modules**, `javac` có cách tìm class file trong class output khác so với chế độ không modular; vì vậy lưu ý `-d` không tự được thêm vào classpath ở mục 4 áp dụng cho chế độ classpath truyền thống.

### 6.4. Generated sources, native headers và resources

- `-d <dir>`: thư mục chứa **class files**.
- `-s <dir>`: thư mục chứa các **source files sinh bởi annotation processor** khi có processor tạo nguồn.
- `-h <dir>`: nơi chứa **native headers** được sinh trong các trường hợp phù hợp.
- Các file cấu hình, ảnh, `.properties` và tài nguyên khác thường do **bước copy resources riêng** quản lý; `javac -d` không mặc định copy toàn bộ nội dung `src/` vào output.

Vì thế, “đã chạy `javac -d build/classes`” không đồng nghĩa với “đã tạo sẵn ứng dụng có đủ tài nguyên và JAR để chạy ở mọi môi trường”.

## 7. Các lỗi phổ biến và cách tìm nguyên nhân

| Tình huống | Vì sao xảy ra | Cách xử lý |
| --- | --- | --- |
| Không thấy `.class` ngay trong `out/` | Class có `package` nên nằm trong `out/<package-path>/` | Kiểm tra khai báo `package`, mở đúng nhánh thư mục |
| `Could not find or load main class` | Dùng sai classpath root hoặc sai tên đầy đủ của lớp | `java -cp build/classes com.example.app.Main` trong ví dụ |
| Biên dịch lượt hai báo thiếu `Greeting` | `-d` không tự thêm output vào classpath biên dịch không modular | Dùng `-cp build/classes` ở lượt hai |
| File `.class` nằm cạnh `.java` | Không truyền `-d` | Dùng `-d out` hoặc `-d build/classes` |
| Output xuất hiện ở vị trí bất ngờ | Đường dẫn `-d` là tương đối và working directory đã thay đổi | Kiểm tra thư mục hiện tại, dùng đường dẫn rõ ràng |
| Biên dịch báo không ghi được file | Sai quyền, đường dẫn đích là file thường, path không hợp lệ hoặc bị hệ thống hạn chế | Kiểm tra đường dẫn, quyền ghi và thông báo lỗi gốc |
| Thêm `-d` xong tưởng sẽ có JAR | `-d` chỉ xuất class files | Chạy `jar` hoặc tác vụ đóng gói của build tool |
| Chạy được trước đây, build mới vẫn dùng lớp cũ | Thư mục output chứa file cũ; lần biên dịch mới không tự dọn dẹp | Kiểm tra classpath, exit code và quy trình clean/build |
| Có class file nhưng chạy lỗi vì resource thiếu | Resource không được `javac` copy theo `-d` | Cấu hình bước copy resources, bảo đảm resource nằm trên runtime classpath phù hợp |

### Vì sao output cũ gây hiểu nhầm?

Giả sử hôm qua đã có `build/classes/com/example/app/Main.class`, nhưng hôm nay sửa code sai cú pháp rồi chạy `javac` thất bại. File `Main.class` hôm qua **có thể vẫn còn nguyên**. Lệnh `java -cp build/classes com.example.app.Main` có thể vẫn chạy bytecode cũ. Do đó:

1. Kiểm tra exit code của `javac`.
2. Biên dịch vào output được quản lý rõ ràng; ở CI/build có thể dùng thư mục sạch để kiểm chứng.
3. Không kết luận “mã hiện tại hợp lệ” chỉ vì lệnh `java` chạy được.
4. Khi đổi package/tên lớp, kiểm tra những `.class` cũ có thể còn tồn tại ở cây output và cần được quy trình clean loại bỏ.

**Lưu ý bảo toàn dữ liệu:** thao tác clean có tính xóa; chỉ xóa thư mục build output mà dự án thực sự sở hữu, không áp dụng lệnh xóa tùy tiện lên thư mục chứa mã nguồn hoặc tài liệu.

## 8. Chọn đường dẫn output trong thực tế

Những tên như `out/`, `classes/`, `build/classes/`, `target/classes/` chỉ là **quy ước**. `javac` không yêu cầu tên đặc biệt; quan trọng là trong một quy trình build, bạn duy trì **cùng một gốc bytecode** giữa biên dịch, chạy, kiểm tra và đóng gói.

Một cấu trúc mẫu cho dự án nhỏ:

```text
project/
├── src/
│   └── com/example/app/Main.java
├── resources/
│   └── application.properties
└── build/
    ├── classes/
    │   └── com/example/app/Main.class
    └── app.jar
```

Đây là cấu trúc mang tính định hướng. `javac -d build/classes` chỉ chịu trách nhiệm **class files**; muốn `application.properties` có trong classpath khi chạy cần một bước copy resource riêng; muốn `app.jar` cần một bước đóng gói riêng. Không tạo các bước ảo mà lệnh `javac` thực tế không làm.

Với dự án nhiều nguồn, đừng tự viết một lệnh `javac` cho từng file và hy vọng tự tìm ra phụ thuộc theo thứ tự. Có thể liệt kê toàn bộ nguồn của lần biên dịch, dùng argument file cho danh sách dài hoặc để Maven/Gradle cấu hình source sets, dependencies và output. Trong mọi trường hợp, cần hiểu **đường dẫn đầu ra** mà compiler thực sự sử dụng.

## 9. Kiểm tra nhanh trước khi kết luận `-d` đã đúng

1. **Lệnh compile có `-d` không?** Nó trỏ tới thư mục nào, tương đối với working directory nào?
2. **Nguồn có `package` nào?** Suy ra đúng nhánh `<output-root>/<package-path>/`.
3. **Những lớp nào được sinh ra?** Có inner class, nhiều top-level types hoặc source được compiler biên dịch thêm không?
4. **Lần compile có thành công không?** Kiểm tra lỗi, cảnh báo quan trọng và exit code thay vì chỉ tìm file tồn tại.
5. **Nếu compile nhiều lượt, compiler có biết class cũ ở đâu?** Thêm `-cp <output-root>` hoặc cấu hình module phù hợp.
6. **Khi chạy, classpath root và tên main class đã đúng?** Dùng `java -cp <output-root> <fully.qualified.Main>`.
7. **Nếu đóng gói, có đưa đúng nội dung *bên trong* output root vào JAR?** Kiểm tra bằng `jar --list`.
8. **Có file cũ hoặc resource chưa được xử lý không?** Phân biệt output do `javac` tạo với các bước build khác.

Một câu để ghi nhớ: **`-d` chọn gốc của cây class files; khai báo `package` xác định các thư mục con; `-cp` hoặc module path giúp compiler/JVM tìm các class files đó về sau.**

### Tham khảo chính thức

Tài liệu lệnh `javac` của Oracle JDK 21: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html — xem các mục `-d`, `--class-path`, `-s` và “Configuring a Compilation”.