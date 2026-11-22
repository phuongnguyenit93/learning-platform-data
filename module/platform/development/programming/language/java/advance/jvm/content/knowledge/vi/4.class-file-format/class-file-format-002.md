# Tương thích phiên bản class và giới hạn của cờ `--enable-preview`

Khi biên dịch Java, `javac` tạo ra các tệp `.class` chứa bytecode và metadata cho JVM. **Một JVM không thể nạp mọi tệp `.class` của mọi bản Java.** Nó kiểm tra phiên bản định dạng class file, cấu trúc và các ràng buộc khác trước khi thực thi. Với tính năng **preview**, còn có một quy tắc nghiêm ngặt hơn: class file phụ thuộc preview của **Java N** chỉ được nạp bằng **Java N** khi preview đã được bật. Việc bật `--enable-preview` trên **Java N+1** không cho phép chạy class file preview của Java N.

Bài này giải thích `major_version`, `minor_version`, nguyên nhân phổ biến của `UnsupportedClassVersionError`, cách `javac --release` tác động đến tương thích, và giới hạn chính xác của `--enable-preview` ở cả lúc **biên dịch** lẫn **chạy**. Các ví dụ dùng JDK 17 để có một trường hợp preview thực tế; bảng và quy tắc chuẩn dựa trên *Java Virtual Machine Specification* (JVMS).

## 1. Tệp `.class` chứa thông tin phiên bản nào?

Trong class file, phần đầu có cấu trúc khái niệm:

```text
Địa chỉ byte   Dữ liệu (big-endian)   Ý nghĩa
0..3           CA FE BA BE          magic number
4..5           u2 minor_version     phiên bản phụ
6..7           u2 major_version     phiên bản chính
8..9           u2 constant_pool_count
...            ...                  constant pool, class metadata, method code...
```

Đây là metadata của **định dạng class file**, không trực tiếp là chuỗi `java -version` của máy biên dịch. JVM sử dụng cặp `major.minor` để quyết định liệu nó có hỗ trợ cách mã hóa class file hay không.

- **`major_version`** cho biết thế hệ định dạng bytecode gắn với một release Java.
- **`minor_version`** là phiên bản phụ; từ Java 12, giá trị đặc biệt **65535** có ý nghĩa dành cho class file **phụ thuộc preview features** của release đó.
- **`CAFEBABE`** là magic number nhận diện định dạng, không phải số phiên bản Java.
- Một tệp `.jar` là container ZIP chứa nhiều tệp `.class` và tài nguyên; **không có một major version duy nhất cho toàn JAR** nếu các class bên trong khác phiên bản.

Ví dụ kết quả từ `javap -verbose Example`:

```text
minor version: 0
major version: 61
```

Nghĩa là định dạng class file **61.0**, tương ứng **Java 17**, không phải “Java phiên bản 61”. Nếu `minor version: 65535` với `major version: 61`, class đó mang dấu phụ thuộc **preview Java 17**.

## 2. Class-file major version và release Java

Các release Java có các mức major phổ biến:

| Java SE / JDK | Class-file major | Ví dụ |
| --- | ---: | --- |
| Java 8 | 52 | `52.0` |
| Java 11 | 55 | `55.0` |
| Java 12 | 56 | `56.0` hoặc `56.65535` nếu phụ thuộc preview |
| Java 17 | 61 | `61.0` hoặc `61.65535` |
| Java 21 | 65 | `65.0` hoặc `65.65535` |
| Java 22 | 66 | `66.0` hoặc `66.65535` |
| Java 23 | 67 | `67.0` hoặc `67.65535` |
| Java 24 | 68 | `68.0` hoặc `68.65535` |
| Java 25 | 69 | `69.0` hoặc `69.65535` |

Với các release Java hiện đại, major của Java N thường là **N + 44** (ví dụ Java 17 → 61); đây là mẹo nhớ, còn **bảng của JVMS** là nguồn chuẩn. Java 1.0/1.1 có chi tiết lịch sử riêng.

**Trường hợp class file thông thường (`minor = 0`):** một JVM mới hơn nhìn chung hỗ trợ major cũ hơn được đặc tả cho release đó. Chẳng hạn, bytecode `61.0` của Java 17 được JVM Java 21 hỗ trợ ở mức **định dạng class file**.

Nhưng “JVM nhận major” **chưa đủ** để bảo đảm chương trình chạy thành công. Vẫn phải xét API có tồn tại không, hệ module, thư viện phụ thuộc, thay đổi hành vi, reflection/encapsulation, native libraries, cấu hình hệ thống và những đặc điểm runtime liên quan.

**Trường hợp major cao hơn JVM hỗ trợ:** Java 17 không nạp được class `65.0` của Java 21. Cờ `--enable-preview` trên Java 17 **không tăng giới hạn major** lên 65.

### 2.1. Minor version: tại sao 65535 đặc biệt?

Theo JVMS, với **major từ 56 trở lên**, minor chỉ có hai giá trị hợp lệ trong định dạng class file: **0** hoặc **65535**.

- `M.0`: class file thông thường, không được đánh dấu phụ thuộc preview bằng cặp phiên bản.
- `M.65535`: class file phụ thuộc preview **của đúng release có major M**.
- `M.1`, `M.2`, ... không phải cách đặt version cho Java hiện đại.
- Những major cũ từ 45 đến 55 có quy tắc minor lịch sử khác; **không được suy diễn 65535 ở mọi class file cũ đều là preview**.

Ví dụ `61.65535` có nghĩa “preview Java 17”, **không** có nghĩa “một bytecode Java 17 có thể chạy trên bất kỳ JDK nào bật preview”.

## 3. Ma trận tương thích quan trọng nhất

Giả sử định dạng class file bình thường đúng quy cách và không vướng vấn đề thư viện/API khác:

| Class file | JVM chạy | Bật `--enable-preview` lúc chạy? | Kết quả ở mức class-version |
| --- | --- | --- | --- |
| `61.0` (Java 17 thường) | Java 17 | Không | **Được phép** |
| `61.0` | Java 21 | Không | **Được phép** |
| `65.0` (Java 21 thường) | Java 17 | Có hay không | **Không**, major quá mới |
| `61.65535` (preview Java 17) | Java 17 | Không | **Không**, preview mặc định tắt |
| `61.65535` | Java 17 | Có | **Được phép** |
| `61.65535` | Java 21 | Không hoặc có | **Không**, preview thuộc release khác |
| `65.65535` (preview Java 21) | Java 21 | Có | **Được phép** |
| `65.65535` | Java 17 | Có | **Không**, major quá mới |

“Được phép” chỉ có nghĩa **qua cổng version/preview**, không cam kết toàn bộ ứng dụng chạy được. Nếu class dùng API chưa có, thư viện còn thiếu, module bị chặn hoặc bytecode sai, chương trình vẫn có thể lỗi khi nạp, liên kết hay thực thi.

Quy tắc cốt lõi với preview class:

```text
class file = N_major . 65535
                       │
                       ▼
Runtime phải là Java N  +  --enable-preview lúc chạy
                       │
         Không được dùng Java N+1, N+2, ...
         dù các runtime mới cũng có --enable-preview
```

Đó là **chủ ý thiết kế**: preview features có thể đổi cú pháp/ngữ nghĩa, được hoàn thiện thành permanent feature, hoặc bị rút bỏ ở một release tiếp theo. JVM không hứa giữ khả năng chạy preview bytecode của bản trước.

## 4. Vì sao phiên bản major gây `UnsupportedClassVersionError`?

Ví dụ bạn cài **JDK 21** trên máy xây dựng, biên dịch mặc định:

```bash
javac App.java
```

Nếu `App.class` mang `major version: 65`, đem chạy bằng Java 17:

```bash
java App
```

Runtime Java 17 chỉ hiểu class-file major tối đa 61; lỗi điển hình là `java.lang.UnsupportedClassVersionError`, với thông điệp kiểu “class file version 65.0 ... recognizes up to 61.0”. Chuỗi lỗi thực tế phụ thuộc JVM và môi trường.

Một cách sửa khi **mã và API thực sự tương thích Java 17** là biên dịch bằng JDK đủ mới với target release 17:

```bash
javac --release 17 App.java
```

Khi đó `javac` tạo class format cho Java 17 và kiểm tra ngôn ngữ/API của release 17. **Không** có cơ sở để tin một ứng dụng sử dụng APIs/cú pháp chỉ có trên Java 21 sẽ vẫn biên dịch thành công bằng `--release 17`.

Nếu ứng dụng bắt buộc cần Java 21, cách xử lý là nâng runtime triển khai lên Java 21 tương ứng (hoặc điều chỉnh/mã hóa lại để tương thích bản đích).

### 4.1. Khác nhau giữa `--release`, `--source`, `--target`

| Tùy chọn `javac` | Điều điều khiển |
| --- | --- |
| `--source N` hoặc `-source N` | Quy tắc cú pháp/ngôn ngữ của Java release N |
| `--target N` | Phiên bản class file được tạo |
| `--release N` | Kết hợp điều kiện nguồn, đích và **bề mặt API công khai** của platform release N mà công cụ hỗ trợ |

Trong các dự án cần hỗ trợ một Java runtime cũ, **ưu tiên `--release N`** khi thích hợp, vì chỉ đặt `--target N` không ngăn mọi trường hợp mã tham chiếu API Java mới hơn tại lúc biên dịch. Khi chạy trên máy cũ, API đó có thể gây `NoSuchMethodError`, `NoClassDefFoundError` hoặc lỗi liên kết tương ứng.

Ví dụ biên dịch mã Java 11-compatible trên JDK hỗ trợ `--release 11`:

```java
public class CompatibleApp {
    public static void main(String[] args) {
        System.out.println("Compatible class");
    }
}
```

Tệp lưu là **`CompatibleApp.java`**:

```bash
javac --release 11 CompatibleApp.java
javap -verbose CompatibleApp
java CompatibleApp
```

Khi `javac` hoàn tất, `javap` cho class này sẽ có:

```text
minor version: 0
major version: 55
```

Stdout của chương trình:

```text
Compatible class
```

Class `55.0` có thể được JVM Java 11 trở lên nạp **ở khía cạnh phiên bản class file**, miễn các yêu cầu runtime còn lại được đáp ứng. Tùy hệ thống bạn có thể cần chỉ định đầy đủ đường dẫn tới `javac`/`java` của đúng JDK, vì nhiều JDK cùng tồn tại.

### 4.2. Build tool cũng phải nhất quán

Trong dự án Maven/Gradle, kiểm tra **Java toolchain**, `sourceCompatibility` / `targetCompatibility`, `--release` tương ứng, bytecode của **thư viện phụ thuộc** và JDK thực sự dùng ở máy chạy.

Ví dụ mô tả cấu hình Gradle Groovy DSL để chọn JDK 17 và target Java 17:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Đoạn trên là **minh họa cho một dự án có plugin `java` phù hợp**, không phải một chương trình Java độc lập. Chọn toolchain giúp điều khiển compiler được dùng, còn `options.release` kiểm soát mục tiêu biên dịch. Cần kiểm tra thêm dependencies, plugins và JVM chạy thử nghiệm/triển khai. Đừng mặc định setting của một IDE đã ảnh hưởng mọi tác vụ build hoặc container.

## 5. Preview feature là gì? Bật cờ được những gì?

**Preview feature** là tính năng Java được đặc tả và hiện thực đủ để thử nghiệm nhưng **chưa được cam kết vĩnh viễn**. Nó có thể là cú pháp ngôn ngữ, khả năng VM hoặc preview API được đưa ra lấy phản hồi trước khi đưa vào chính thức.

Hai bước có thể cần trong vòng đời chương trình:

1. **Compile time:** bật preview trên đúng bản `javac` nếu mã sử dụng preview feature được bản JDK đó hỗ trợ.
2. **Run time:** bật preview trên **đúng bản Java** khi chạy những class files yêu cầu preview, hoặc cần thực thi tính năng runtime preview.

Một số tính năng về sau trở thành chuẩn và không cần `--enable-preview` trong phiên bản đã chính thức hóa. Một tính năng preview của Java N cũng có thể bị thay đổi hoặc bị loại bỏ ở N+1; không nên phụ thuộc vào một preview feature như hợp đồng tương thích lâu dài.

### 5.1. Cú pháp biên dịch điển hình

Khi dùng **JDK 17** và sử dụng tính năng preview ở Java 17:

```bash
javac --enable-preview --release 17 Preview17.java
```

Cách tương đương thường dùng với compiler thích hợp:

```bash
javac --enable-preview --source 17 Preview17.java
```

Với `javac` hiện đại, muốn bật preview của một release phải chọn **release hiện tại mà compiler đó hỗ trợ preview**. Ví dụ, `javac` từ JDK 21 **không thể** dùng `--enable-preview --release 17` để tái tạo hay bật preview của Java 17. Lệnh biên dịch preview Java 17 ở trên cần **JDK 17**.

Nếu chỉ viết:

```bash
javac --enable-preview Preview17.java
```

Cú pháp cụ thể về việc yêu cầu `--release`/`--source` khi bật preview phụ thuộc quy tắc của `javac` tương ứng; cách minh bạch, dễ tái lập là **nêu rõ `--enable-preview --release <phiên bản JDK hiện tại>`** như ví dụ.

### 5.2. Cú pháp chạy

Nếu class file đã được đánh dấu phụ thuộc preview của **Java 17**, chạy bằng **Java 17**:

```bash
java --enable-preview Preview17
```

Chạy bằng Java 17 nhưng bỏ cờ có thể gặp `UnsupportedClassVersionError` báo preview chưa bật. Chạy bằng Java 21, dù có `--enable-preview`, vẫn không được nạp class `61.65535`: đó là preview **Java 17**, không phải preview Java 21.

`--enable-preview` áp dụng cho preview features **của release đang dùng**; không cho chọn riêng từng preview feature. Cờ này cũng không đồng nghĩa với việc kích hoạt incubator modules, truy cập API nội bộ, mở module packages hay bỏ qua class verifier.

## 6. Ví dụ preview Java 17: nhìn thấy `61.65535`

Java 17 có **pattern matching for switch** ở trạng thái *preview*. Dùng ví dụ này **trên JDK 17** để minh họa ranh giới thực tế.

Tạo file **`Preview17.java`**:

```java
public class Preview17 {

    static String describe(Object value) {
        return switch (value) {
            case String text -> "String: " + text;
            case Integer number -> "Integer: " + number;
            default -> "Other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe("JVM"));
        System.out.println(describe(42));
    }
}
```

Biên dịch bằng **JDK 17**:

```bash
javac --enable-preview --release 17 Preview17.java
```

Compiler có thể in ghi chú/cảnh báo liên quan đến preview và tùy chọn chi tiết hóa cảnh báo; đó là **diagnostic trên stderr**, không phải stdout của chương trình. Sau khi biên dịch, kiểm tra metadata:

```bash
javap -verbose Preview17
```

Các dòng phiên bản cần thấy:

```text
minor version: 65535
major version: 61
```

Chạy trên **Java 17**:

```bash
java --enable-preview Preview17
```

**Stdout chính xác:**

```text
String: JVM
Integer: 42
```

Giải thích:

1. `switch` dùng `case String text` và `case Integer number` là pattern matching for switch, preview ở Java 17.
2. `javac` JDK 17 khi biên dịch theo chế độ preview đánh dấu class dùng tính năng này bằng phiên bản **61.65535**.
3. Java 17 chạy class đó khi bật preview; không cần “hai lớp runtime” hoặc dịch lại ngay trong lệnh `java`.
4. Nếu chuyển `Preview17.class` sang Java 21 thì JVM Java 21 **không được nạp nó**, dù bạn chạy `java --enable-preview Preview17`.
5. Muốn chạy trên Java 21, bạn phải **biên dịch lại từ source với compiler và cú pháp/feature hợp lệ của Java 21**, rồi kiểm tra lại major/minor. Không có lời hứa tính năng preview cùng hành vi giữa hai release.

**Chú ý độ tin cậy:** ví dụ yêu cầu cài JDK 17 cụ thể; compiler JDK 24 hoặc JDK 21 không thể đóng vai trò “compiler preview Java 17” bằng cách đặt lại `--release 17`. Đây là giới hạn thật của preview, không phải lỗi của mã nguồn.

### 6.1. Ba phép thử lỗi có mục đích

Sau khi bạn có `Preview17.class` dạng `61.65535`:

**Thử 1: Java 17 không bật preview**

```bash
java Preview17
```

Kết quả mong đợi: JVM từ chối nạp class, thường là `UnsupportedClassVersionError` với nội dung giải thích preview chưa bật. **Không kỳ vọng stdout chương trình** vì `main` chưa được thực thi.

**Thử 2: Java 17 bật preview**

```bash
java --enable-preview Preview17
```

Kết quả: chạy thành công và in hai dòng đã nêu.

**Thử 3: Java 21 bật preview**

```bash
java --enable-preview Preview17
```

Nếu `java` lúc này thực sự là Java 21, class `61.65535` **không hợp lệ cho release Java 21**. Việc Java 21 bình thường hỗ trợ nhiều class major cũ **không** mở rộng sang preview class của Java 17. Lỗi cụ thể có thể thay đổi, nhưng runtime phải từ chối theo quy tắc JVMS.

Khi thử, hãy dùng đường dẫn tuyệt đối hoặc thiết lập `JAVA_HOME`/`PATH` một cách rõ ràng để bảo đảm lệnh đang gọi **đúng runtime muốn kiểm tra**.

## 7. `--enable-preview` KHÔNG giải quyết những gì?

| Tình huống | Vì sao cờ không giúp? | Hướng xử lý phù hợp |
| --- | --- | --- |
| Java 17 chạy class `65.0` | Major 65 lớn hơn mức runtime Java 17 hỗ trợ | Nâng runtime lên Java 21 hoặc biên dịch lại target 17 nếu source/API cho phép |
| Java 21 chạy class `61.65535` | Preview bytecode gắn với đúng Java 17 | Biên dịch lại source theo Java 21 hợp lệ; không thể bật preview cũ trên Java 21 |
| `javac` JDK 21 bật preview của Java 17 | Compiler chỉ hỗ trợ preview của chính release hiện tại | Dùng JDK 17 để biên dịch preview Java 17 hoặc cập nhật mã sang Java 21 |
| Class có lỗi verification/format | Cờ không bỏ qua bộ kiểm tra class file | Sửa bytecode, generator/instrumentation hoặc dependency |
| Thiếu thư viện hay API lúc chạy | Cờ không tự cung cấp module/JAR hoặc API | Đồng bộ dependency, module path/classpath, release API |
| Truy cập package nội bộ bị module chặn | Preview khác với mở đóng gói module | Dùng public API hoặc cấu hình module phù hợp khi thực sự cần |
| Dùng **incubator module** như Vector API trong một số JDK | Incubator không tự bật chỉ nhờ preview flag | Xem tài liệu module và cấu hình `--add-modules` riêng |
| Muốn chạy chương trình preview không sửa mã về lâu dài | Preview không cam kết tương thích lâu dài | Theo dõi trạng thái từng release và chuyển sang API/cú pháp chuẩn khi sẵn sàng |

Đặc biệt, **`--enable-preview` không phải “bỏ giới hạn kiểm tra phiên bản”**. Nó thay đổi trạng thái kích hoạt **những preview features được chính runtime/compiler của release đó hỗ trợ**, và runtime vẫn kiểm tra major/minor chặt chẽ.

## 8. Preview API, preview language feature và class file

Một class file `M.65535` có thể được tạo khi compiler cần ghi nhận phụ thuộc preview, chẳng hạn source sử dụng **preview language feature**. Không nên cho rằng mọi tệp `.class` được biên dịch trong một lệnh có `--enable-preview` đều nhất thiết phải có minor `65535` nếu chúng không phụ thuộc preview; **luôn xem phiên bản thực tế của từng class file**.

Các khía cạnh cần phân biệt:

- **Preview language feature:** cú pháp/biểu thức mới; compiler có thể phải đánh dấu output class file là preview-dependent.
- **Preview VM feature:** khả năng của JVM được xác định bởi JVMS của release đó; chạy phụ thuộc runtime hỗ trợ và trạng thái bật preview.
- **Preview API:** API được trình bày là preview của release; việc sử dụng có điều kiện/cảnh báo của compiler và quy tắc triển khai riêng.
- **Incubator API/module:** cơ chế thử nghiệm khác; `--enable-preview` **không** tự động cấp quyền truy cập hoặc giải quyết cấu hình module cho incubator.

Không thể xác nhận “class này dùng preview hay không” chỉ bằng cách nhìn chuỗi ký tự `--enable-preview` trong một file build. Cần kiểm tra cả **source, dependencies, compiler diagnostics và class-file metadata**, đặc biệt khi các tác vụ build biên dịch nhiều module ở các release khác nhau.

### 8.1. Preview đã trở thành chuẩn thì sao?

Khi một tính năng được chuẩn hóa trong bản Java mới, việc dùng **hình thức cú pháp/API được bản mới công nhận** có thể không cần preview flag nữa. Tuy nhiên, **class preview được tạo ở bản cũ vẫn mang minor 65535 của bản cũ** và không tự biến thành class thường.

Ví dụ pattern matching for `switch` trở thành permanent từ Java 21; dù source tương đương có thể biên dịch trên JDK 21 mà không dùng preview cho tính năng đó, tệp `Preview17.class` đã đánh dấu `61.65535` **không đổi metadata** chỉ vì đem tới Java 21.

**Cách đúng:** biên dịch lại source trên toolchain mới với cấu hình mới, sau đó kiểm tra class format được tạo.

## 9. Tương thích giữa nhiều phiên bản và JAR nhiều release

Với thư viện, có thể gặp **multi-release JAR**: một JAR có class cơ sở và class chuyên biệt ở đường dẫn dạng:

```text
lib.jar
├── META-INF/MANIFEST.MF     (Multi-Release: true)
├── com/example/Api.class
└── META-INF/versions/17/com/example/Api.class
```

Runtime phù hợp có thể chọn class chuyên biệt cho phiên bản hỗ trợ; cấu trúc cụ thể và quy tắc lựa chọn theo tài liệu multi-release JAR. Cơ chế này giúp cung cấp implementation theo phiên bản, **không** biến preview bytecode Java 17 thành mã chạy hợp lệ trên Java 21.

Ví dụ, nếu class trong `META-INF/versions/17` là `61.65535`, bản đó vẫn chịu quy tắc **preview đúng release Java 17**. Khi dùng multi-release JAR, cần thiết kế từng class/path đúng target JVM và kiểm tra class được runtime thực sự chọn.

Một JAR có thể chứa một class `65.0` ở nhánh dành cho Java 21 và class `55.0` ở nhánh cơ sở cho Java 11; điều đó không có nghĩa Java 11 được phép nạp trực tiếp class major 65. Đường dẫn và metadata manifest quyết định khả năng lựa chọn bản thích hợp.

## 10. Kiểm tra phiên bản thực sự của toolchain, class và runtime

### 10.1. Bộ lệnh cơ bản

```bash
# Java runtime đang được gọi
java -version

# Compiler đang được gọi
javac -version

# Chi tiết header/class bytecode; lệnh cần JDK
javap -verbose -p CompatibleApp

# Trên JAR, kiểm tra class cụ thể sau khi giải nén theo cách phù hợp
jar tf application.jar
```

`java` và `javac` có thể đến từ **hai JDK khác nhau** nếu `PATH` hoặc IDE/CI không nhất quán. Cần xác minh đường dẫn executable và cấu hình toolchain trong CI/container.

`javap` hiển thị metadata class (ví dụ major/minor, constant pool, method code), nhưng JVM đang chạy là một thành phần khác. `javap` từ JDK mới có thể đọc định dạng không chạy được trên Java runtime cũ.

### 10.2. Cách đọc ba dạng lỗi

**Lỗi A — class file quá mới:**

```text
... UnsupportedClassVersionError ...
... class file version 65.0 ...
... recognizes class file versions up to 61.0 ...
```

Đây là **minh họa mẫu thông báo**, không phải stdout cố định của mọi JVM. Runtime ở mức Java 17 gặp class Java 21 thường sẽ báo chênh lệch major 65 và 61. Sửa target/build hoặc runtime.

**Lỗi B — class file preview nhưng chưa bật:**

```text
... UnsupportedClassVersionError ...
... class file version 61.65535 ...
... preview features are not enabled ...
```

Kiểm tra đúng Java 17 và thêm `--enable-preview` **lúc chạy**, nếu bạn thật sự chấp nhận dùng preview của release đó.

**Lỗi C — preview thuộc release khác:**

```text
... UnsupportedClassVersionError ...
... class file version 61.65535 ...
... preview features ... unsupported for this runtime ...
```

Trên Java 21, class `61.65535` không chạy được dù bật preview. Sửa bằng cách **biên dịch lại từ mã nguồn tương thích Java 21** hoặc chạy đúng Java 17 với preview.

### 10.3. Quy trình chẩn đoán 5 bước

1. **Xác định file thực sự được nạp:** classpath/module path, JAR và version-specific path; không đoán dựa vào tên thư viện.
2. **Đọc major/minor:** dùng `javap -verbose` hoặc trình đọc class-file metadata phù hợp.
3. **Kiểm tra runtime thực sự:** `java -version`, toolchain/launcher của IDE, CI image/container.
4. **Phân nhánh:** major quá cao, preview minor 65535 sai release/chưa bật, hay lỗi khác như thiếu API/dependency?
5. **Sửa ở đúng lớp:** chỉnh `--release` khi source/APIs cho phép; đồng bộ JDK lúc build và chạy; biên dịch lại preview source trên đúng release; cập nhật dependency, sau đó kiểm tra lại class thực tế.

Không nên lấy `--enable-preview` làm một bước “thử đại” mỗi khi gặp `UnsupportedClassVersionError`. Thường chỉ nhìn **major.minor** đã đủ phân biệt hai trường hợp rất khác nhau.

## 11. Áp dụng vào build và triển khai

Một ứng dụng cần hỗ trợ nhiều runtime nên đặt **Java target nhỏ nhất** theo yêu cầu sản phẩm, dùng CI thử nghiệm thực trên các runtime đích, và thiết kế phụ thuộc tương thích. Nếu chọn preview feature để học hoặc thử nghiệm, cần khóa công cụ và runtime vào đúng **Java release**, đồng thời có kế hoạch chuyển đổi khi preview đổi trạng thái.

Checklist cho developer:

- Xác định version thực của `java` và `javac` ở máy local, CI và container.
- Chọn `--release N` hoặc toolchain theo runtime muốn hỗ trợ; kiểm tra dependencies cũng tương thích.
- Nếu dùng preview: khai báo release cụ thể của JDK compiler, dùng `--enable-preview` đúng lúc biên dịch/chạy và chạy test trên **chính release đó**.
- Xem `javap -verbose` ở class quan trọng; với JAR/multi-module kiểm tra class files được chọn thay vì chỉ một class.
- Khi nâng JDK, **biên dịch lại preview source**; không mang nguyên `N.65535` sang N+1.
- Với tính năng đã trở thành chuẩn, cập nhật cú pháp/toolchain theo release mới rồi xác minh `minor` của class file được tạo.
- Giữ build có khả năng tái lập: ghi rõ JDK/toolchain version, release flags và image triển khai.

## 12. Bài tập tự kiểm tra (có đáp án)

**Câu 1.** Class file có `major 61`, `minor 0`. Trên Java 21, có cần `--enable-preview` không?

**Đáp án:** **Không** vì class không đánh dấu phụ thuộc preview. Java 21 chấp nhận class major 61 ở mức định dạng; còn khả năng chạy trọn vẹn phụ thuộc APIs/libraries/runtime.

**Câu 2.** Class file có `major 61`, `minor 65535`. Trên Java 21 thêm `--enable-preview` có chạy được không?

**Đáp án:** **Không.** Đó là preview **Java 17**; class phải chạy bằng Java 17 với preview enabled, hoặc biên dịch lại source cho Java 21.

**Câu 3.** Dùng `javac` JDK 21 để chạy `--release 17 --enable-preview` có thể bật preview Java 17 không?

**Đáp án:** **Không**. Preview chỉ được compiler bật cho release hiện tại mà compiler đó hỗ trợ. Với source preview Java 17, cần compiler JDK 17 (hoặc chuyển mã sang cấu trúc được JDK 21 chấp nhận).

**Câu 4.** Vì sao `javac --target 11` có thể là lựa chọn chưa đủ khi hỗ trợ Java 11?

**Đáp án:** Vì target class format không nhất thiết chặn tham chiếu tới những API nền tảng chỉ có trên JDK biên dịch mới hơn. `--release 11` kiểm soát cả ngôn ngữ, target và bề mặt API được hỗ trợ.

**Câu 5.** Nếu chạy class `65.0` trên JVM Java 17 và nhận `UnsupportedClassVersionError`, có nên chỉ thêm `--enable-preview`?

**Đáp án:** **Không.** Đây là vấn đề **major 65 > 61**, không phải preview minor 65535. Nâng runtime hoặc biên dịch với target 17 nếu mã và dependencies cho phép.

**Câu 6.** Pattern matching for switch đã thành chuẩn ở Java 21. Có thể chạy file `61.65535` đã biên dịch Java 17 preview trực tiếp trên Java 21 không?

**Đáp án:** **Không.** Class-file minor vẫn đánh dấu preview Java 17; cần **biên dịch lại** để tạo class-file version thích hợp.

## Ghi nhớ cuối bài

- **`major.minor` mô tả định dạng class file**; major liên quan release Java, minor `65535` từ Java 12 biểu thị phụ thuộc preview của chính release đó.
- **Class thường `N.0`** có thể được runtime mới hơn nạp ở mức định dạng, nhưng compatibility của API/module/dependency vẫn phải kiểm tra.
- **Class preview `N.65535`** chỉ được nạp trên **Java N với `--enable-preview`**. Runtime mới hơn dù có preview flag cũng không nhận preview class của N.
- **`--release`** hữu ích cho target Java cũ khi không phụ thuộc preview; **`--enable-preview`** là cơ chế thử nghiệm preview của đúng JDK, không phải công cụ chuyển đổi bytecode, backport tính năng hoặc bỏ qua verification.

### Tài liệu chuẩn

- [JVMS Java SE 21 — ClassFile structure (`4.1`), version và preview](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.1).
- [JVMS Java SE 21 — Preview features (`1.5`)](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-1.html#jvms-1.5).
- [JEP 12 — Preview Language and VM Features](https://openjdk.org/jeps/12).
- [JDK 17 `javac` manual: `--release`, `--enable-preview`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html).
- [JDK 17 `java` launcher manual: `--enable-preview`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [JDK 17 `javap` manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
