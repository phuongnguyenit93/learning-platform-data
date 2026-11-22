# Đặt mức ngôn ngữ và API đích bằng `javac --release 17`

Khi phát triển ứng dụng Java, phiên bản JDK dùng để **biên dịch** có thể mới hơn phiên bản Java dùng để **chạy** ứng dụng. Ví dụ, máy lập trình viên cài JDK 21 hoặc mới hơn, nhưng máy chủ triển khai vẫn dùng Java 17. Trong trường hợp này, chỉ chạy `javac` theo mặc định là chưa đủ: trình biên dịch có thể chấp nhận cú pháp và API chỉ tồn tại ở phiên bản JDK mới.

Tùy chọn **`javac --release 17`** giúp biên dịch mã nguồn theo mức tương thích Java 17. Bài học này tập trung vào cách dùng tùy chọn đó để kiểm soát đồng thời cú pháp ngôn ngữ, API của nền tảng Java và định dạng bytecode.

## 1. `--release 17` thực sự thiết lập những gì?

Giả sử chạy trình biên dịch của một JDK đủ mới và có hỗ trợ đích `17`:

```bash
javac --release 17 Main.java
```

Trình biên dịch sẽ áp dụng ba ràng buộc chính:

| Khía cạnh | Ý nghĩa khi chọn `--release 17` |
| --- | --- |
| **Ngôn ngữ Java** | Chỉ chấp nhận các tính năng ngôn ngữ chính thức có trong Java 17 trở về trước; cú pháp của các phiên bản sau không được chấp nhận. |
| **API nền tảng** | Kiểm tra mã nguồn dựa trên những API công khai, được cung cấp cho bản phát hành Java 17. Một phương thức mới xuất hiện ở Java 21 không thể được gọi như thể đã có trong Java 17. |
| **Bytecode** | Tạo tệp `.class` với định dạng tương thích Java 17, thông thường có **class file major version 61**. |

Có thể hình dung luồng biên dịch như sau:

```text
JDK dùng để biên dịch (có hỗ trợ --release 17)
                         |
                         v
                javac --release 17
                         |
          +--------------+--------------+
          |              |              |
     Cú pháp Java 17  API Java 17   Bytecode 61
          |              |              |
          +--------------+--------------+
                         |
                         v
              Ứng dụng hướng tới Java 17
```

Điểm quan trọng: `--release` là **tùy chọn của trình biên dịch `javac`**. Nó không chuyển JDK đang cài thành JDK 17 và không tự khởi chạy chương trình bằng Java 17.

## 2. Chuẩn bị môi trường thực hành

Đầu tiên, mở terminal và kiểm tra công cụ đang được gọi:

```bash
javac -version
java -version
```

`javac` phải đến từ một **JDK**, không phải chỉ có môi trường chạy Java. Để biên dịch với `--release 17`, hãy dùng một phiên bản `javac` có hỗ trợ target 17; thường là JDK 17 hoặc JDK mới hơn vẫn giữ mức hỗ trợ này. Xem các mức đích mà bản `javac` đang dùng thực sự hỗ trợ bằng:

```bash
javac --help
```

Tìm phần mô tả tùy chọn `--release` và danh sách *Supported releases*. Danh sách phụ thuộc vào phiên bản trình biên dịch, vì vậy không nên mặc định rằng mọi JDK đều hỗ trợ mọi bản phát hành cũ.

Hai lệnh `javac -version` và `java -version` có thể trả về các phiên bản khác nhau nếu `PATH` hoặc cách cài đặt JDK chưa thống nhất. Điều này đặc biệt cần chú ý khi kiểm thử chương trình trên Java 17.

## 3. Thực hành: biên dịch chương trình dành cho Java 17

Tạo cấu trúc thư mục:

```text
java17-release-demo/
└── src/
    └── com/
        └── example/
            └── Main.java
```

Nội dung `src/com/example/Main.java`:

```java
package com.example;

import java.util.List;

public class Main {
    record Lesson(String title, int level) {}

    public static void main(String[] args) {
        var lessons = List.of(
                new Lesson("Làm quen với --release", 17),
                new Lesson("Biên dịch tương thích", 17)
        );

        for (var lesson : lessons) {
            System.out.println(lesson.title() + " - Java " + lesson.level());
        }
    }
}
```

Ví dụ sử dụng `record` (tính năng ngôn ngữ chính thức từ Java 16), `var` (từ Java 10) và `List.of` (API từ Java 9). Tất cả đều hợp lệ khi chọn đích Java 17.

Tại thư mục gốc `java17-release-demo`, tạo thư mục đầu ra rồi biên dịch:

```bash
mkdir out
javac --release 17 -encoding UTF-8 -d out src/com/example/Main.java
```

Giải thích các phần của lệnh:

| Thành phần | Tác dụng |
| --- | --- |
| `javac` | Gọi trình biên dịch Java. |
| `--release 17` | Chọn mức ngôn ngữ, API nền tảng và bytecode của Java 17. |
| `-encoding UTF-8` | Đọc tệp nguồn theo UTF-8, tránh sai ký tự tiếng Việt khi môi trường có mã hóa mặc định khác. |
| `-d out` | Đưa các tệp `.class` vào thư mục `out`, theo cấu trúc package. |
| `src/com/example/Main.java` | Tệp nguồn cần biên dịch. |

Sau khi biên dịch thành công, tệp `out/com/example/Main.class` được tạo ra; lớp `Lesson` lồng bên trong cũng có tệp `.class` riêng. Chạy chương trình:

```bash
java -cp out com.example.Main
```

Kết quả dự kiến:

```text
Làm quen với --release - Java 17
Biên dịch tương thích - Java 17
```

`-cp out` đưa thư mục chứa lớp đã biên dịch vào classpath; `com.example.Main` là tên lớp đầy đủ gồm cả package. Để **xác nhận khả năng chạy trên Java 17**, dùng trình chạy `java` của Java 17 cho lệnh này. Chạy thành công trên JDK mới hơn thôi chưa chứng minh chương trình tương thích toàn bộ với môi trường Java 17.

## 4. Kiểm tra phiên bản bytecode

Lệnh `javap` có thể đọc thông tin trong tệp `.class`:

```bash
javap -verbose -classpath out com.example.Main
```

Trong kết quả, tìm dòng:

```text
major version: 61
```

Java 17 dùng class file major version **61**. Đây là một dấu hiệu kỹ thuật cho thấy tệp lớp có định dạng Java 17. Tuy nhiên, **major version đúng không đồng nghĩa mọi lời gọi API đều chạy được**: còn phải xét các thư viện phụ thuộc và môi trường thực thi, như phần dưới đây.

## 5. Thử ràng buộc API: vì sao `--release` hữu ích?

Giả sử viết tệp `src/com/example/ApiCheck.java`:

```java
package com.example;

import java.util.List;

public class ApiCheck {
    public static void main(String[] args) {
        var names = List.of("An", "Bình");
        System.out.println(names.getFirst());
    }
}
```

Phương thức **`List.getFirst()`** được bổ sung vào API nền tảng từ **Java 21**. Vì Java 17 chưa có phương thức này, lệnh sau sẽ không biên dịch được:

```bash
javac --release 17 -encoding UTF-8 -d out src/com/example/ApiCheck.java
```

Trình biên dịch thường báo lỗi dạng `cannot find symbol` tại `getFirst()`. Đây là lỗi **có ích**: vấn đề tương thích đã được phát hiện khi biên dịch, trước khi đưa ứng dụng lên môi trường Java 17.

Có thể sửa thành API đã có từ lâu và vẫn hợp lệ trong Java 17:

```java
System.out.println(names.get(0));
```

Sau đó chạy lại lệnh biên dịch với `--release 17`.

**Nếu chỉ dùng `-source 17 -target 17` trên một JDK mới hơn:** trình biên dịch có thể vẫn nhìn thấy API của chính JDK mới đó, dù tạo bytecode phiên bản 61. Vì vậy một lời gọi API mới vẫn có nguy cơ lọt qua bước biên dịch rồi gây lỗi khi chạy trên Java 17. `--release 17` giải quyết đúng khoảng trống này đối với API nền tảng Java.

## 6. So sánh `--release`, `-source` và `-target`

Ba tùy chọn dễ bị nhầm lẫn vì đều liên quan tới phiên bản Java:

| Tùy chọn | Kiểm soát trực tiếp | Hạn chế nếu dùng riêng |
| --- | --- | --- |
| `--release 17` | Mức cú pháp, API nền tảng và bytecode của Java 17. | Không xác thực tính tương thích của mọi thư viện bên ngoài hoặc hành vi khi chạy. |
| `-source 17` | Phiên bản cú pháp ngôn ngữ Java. | Không tự giới hạn API nền tảng về Java 17. |
| `-target 17` | Phiên bản định dạng tệp `.class` được tạo. | Không tự giới hạn API nền tảng hoặc thay thế việc chọn đúng mức nguồn. |

Với nhu cầu viết ứng dụng chạy trên Java 17, cú pháp nên ưu tiên là:

```bash
javac --release 17 -d out src/com/example/Main.java
```

Không kết hợp `--release` với `-source` hoặc `-target` trong cùng một lần gọi; `javac` coi đây là các tùy chọn xung đột. Nếu cần thiết lập đường dẫn thư viện dự án, vẫn có thể dùng các tùy chọn classpath hoặc module path tương ứng, tùy cách tổ chức ứng dụng.

## 7. Những gì `--release 17` chưa đảm bảo

`--release 17` là một lớp bảo vệ quan trọng khi biên dịch, nhưng không phải là phép kiểm tra tương thích hoàn chỉnh cho toàn bộ ứng dụng.

**Thư viện bên ngoài:** Nếu ứng dụng phụ thuộc vào JAR do bên thứ ba cung cấp, cần chọn phiên bản thư viện có hỗ trợ Java 17. `--release` không tự hạ phiên bản bytecode hoặc thay thế những API mà thư viện đó sử dụng. Một thư viện được biên dịch cho JDK mới hơn vẫn có thể gây lỗi khi chạy bằng Java 17.

**Hành vi khi chạy:** Trình biên dịch không mô phỏng chính xác môi trường chạy, cấu hình máy chủ, hệ điều hành, thư viện native, kết nối mạng, tệp tin hay quyền truy cập. Chương trình cần được chạy và kiểm thử trên Java 17 thực tế nếu đây là phiên bản sẽ triển khai.

**Cấu hình khởi chạy:** `javac --release 17` không chọn tự động bản `java` nào sẽ chạy ứng dụng. Khi trên máy có nhiều JDK, cần kiểm tra đường dẫn và phiên bản trình chạy.

**Tính năng preview:** Các tính năng preview chưa trở thành tính năng chính thức không nên được xem là một phần của hợp đồng tương thích Java 17 thông thường. Với mục tiêu triển khai ổn định trên Java 17, dùng các tính năng chính thức và biên dịch bằng `--release 17` như các ví dụ trên.

Với dự án có nhiều module, còn phải kiểm tra các module và dependency tương ứng; đặt `--release 17` cho phần mã nguồn đang biên dịch không chứng minh mọi thành phần phụ thuộc đều chạy được trên Java 17.

## 8. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `error: release version 17 not supported` | Bản `javac` đang dùng không hỗ trợ target 17, thường vì JDK quá cũ. | Chọn một JDK có hỗ trợ `--release 17`; kiểm tra `javac -version` và `javac --help`. |
| `javac` không được nhận diện | Chưa cài JDK hoặc thư mục `bin` của JDK chưa nằm trong `PATH`. | Kiểm tra cài đặt JDK và cấu hình `PATH`; mở lại terminal sau khi đổi cấu hình. |
| `cannot find symbol` tại một API mới | API đó chưa tồn tại trong Java 17. | Tra phiên bản xuất hiện của API và dùng phương án có trong Java 17; ví dụ `get(0)` thay cho `List.getFirst()`. |
| Lỗi vì dùng đồng thời `--release` với `-source`/`-target` | Đưa vào các tùy chọn xung đột. | Giữ `--release 17` và bỏ `-source`, `-target` tương ứng. |
| `UnsupportedClassVersionError` khi chạy | Một lớp của chương trình hoặc dependency được biên dịch cho Java mới hơn runtime đang dùng. | Xác định tệp lớp gây lỗi, chỉnh bản biên dịch/dependency và chạy trên Java 17 để xác nhận. |
| `ClassNotFoundException` khi chạy | Thiếu classpath/module path hoặc dùng sai tên lớp, package. | Kiểm tra `-d`, `-cp` và tên lớp đầy đủ; với module dùng cấu hình module path thích hợp. |

Trên Windows có thể dùng `where.exe javac` và `where.exe java` để xem các chương trình có trong `PATH`; trên macOS hoặc Linux thường dùng `which javac` và `which java`. Khi nghi ngờ hai lệnh đang trỏ đến hai JDK khác nhau, kiểm tra cả đường dẫn lẫn thông tin phiên bản.

## 9. Bài tập tự thực hành

1. Tạo và biên dịch `Main.java` bằng `javac --release 17 -encoding UTF-8 -d out ...`, sau đó chạy trên Java 17.
2. Dùng `javap -verbose` kiểm tra class file major version; kết quả mong đợi là `61`.
3. Thử biên dịch `ApiCheck.java` có `List.getFirst()` với `--release 17`. Quan sát lỗi API không tồn tại, sau đó thay bằng `List.get(0)` và biên dịch lại.
4. Nếu máy có JDK mới hơn Java 17, so sánh khả năng truy cập `List.getFirst()` giữa lệnh biên dịch thông thường và lệnh có `--release 17`; ghi lại vì sao chỉ nhìn bytecode version là chưa đủ.

Khi viết ứng dụng phải vận hành trên Java 17, hãy thống nhất **đích biên dịch** là `javac --release 17`, chọn dependency hỗ trợ Java 17 và xác minh trên **runtime Java 17**. Ba điều này cùng nhau giúp giảm rủi ro chương trình biên dịch thành công trên máy phát triển nhưng thất bại khi triển khai.
