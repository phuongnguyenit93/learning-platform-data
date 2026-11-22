# Phối hợp `--release` với `module-info` và JAR đa phiên bản

Java 9 đưa vào ba khả năng thường được dùng cùng nhau khi phát hành thư viện Java: biên dịch theo một phiên bản Java cụ thể bằng `javac --release`, khai báo module bằng `module-info.java`, và đóng gói nhiều bản triển khai của cùng một lớp trong Multi-Release JAR (MRJAR). Khi phối hợp đúng, một JAR có thể giữ API và module ổn định ở mức nền, đồng thời chọn phần triển khai phù hợp với phiên bản JVM đang chạy.

Ví dụ dưới đây lấy Java 9 làm mức nền để minh họa các tính năng được giới thiệu ở Java 9, sau đó bổ sung bản triển khai tối ưu cho Java 17 trở lên. Trong dự án thực tế, hãy chọn mức nền theo các runtime mà sản phẩm còn cam kết hỗ trợ.

## 1. Ba thành phần giải quyết ba vấn đề khác nhau

| Thành phần | Vai trò | Điều cần kiểm soát |
|---|---|---|
| `javac --release N` | Biên dịch mã nguồn cho Java SE release N | Cú pháp ngôn ngữ, phiên bản bytecode và tập API Java SE được phép sử dụng |
| `module-info.java` | Khai báo module và ranh giới truy cập | Tên module, `requires`, `exports`, `opens`, `uses`, `provides` |
| Multi-Release JAR | Lưu lớp hoặc tài nguyên thay thế theo phiên bản Java | Manifest, thư mục `META-INF/versions/N` và quy tắc chọn entry lúc chạy |

### `--release` kiểm soát cả ngôn ngữ, bytecode và API

Khi chạy bằng JDK mới, `javac --release 9` yêu cầu compiler biên dịch theo Java 9: chỉ dùng cú pháp được Java 9 hỗ trợ, tạo bytecode tương thích với Java 9 và kiểm tra lời gọi API theo API Java SE của release 9. Tương tự, `--release 17` tạo đầu ra hướng tới Java 17.

Điểm quan trọng là `--release` kiểm tra cả bề mặt API. Chỉ dùng `-source` và `-target` trên JDK mới có thể vẫn cho phép mã nguồn tham chiếu API mới hơn mức runtime đích có, dẫn đến lỗi khi chạy. Vì vậy, khi cần phát hành cho một release cụ thể, ưu tiên `--release`.

`--release` là tùy chọn của compiler. Nó không chạy chương trình, không đóng gói JAR và không tự làm cho thư viện phụ thuộc tương thích với runtime đích. Các dependency cũng cần có bytecode và API phù hợp.

### `module-info.java` mô tả module

Một module có tên cần descriptor `module-info.java`. Ví dụ:

```java
module com.acme.greetings {
    exports com.acme.greetings;
}
```

`exports` cho phép module khác truy cập các kiểu public trong package được nêu. `requires` khai báo module phụ thuộc; `opens` điều khiển truy cập reflective; `uses` và `provides` mô tả điểm mở rộng qua ServiceLoader.

Với JAR có Java 9 là mức nền, biên dịch descriptor cùng source set nền bằng `--release 9`. File `module-info.class` được đặt ở gốc JAR. Khi chạy trên module path, JVM nhận diện JAR này là named module.

### Multi-Release JAR chọn lớp theo JVM

MRJAR chứa lớp nền ở đường dẫn thông thường và các lớp thay thế trong `META-INF/versions/<N>/`. Manifest phải có thuộc tính:

```text
Manifest-Version: 1.0
Multi-Release: true

```

Ví dụ, entry `META-INF/versions/17/com/acme/greetings/Greeting.class` thay thế entry nền `com/acme/greetings/Greeting.class` trên JVM Java 17 trở lên. JVM chọn thư mục có số phiên bản cao nhất không vượt quá feature version của runtime. Runtime thấp hơn tiếp tục dùng lớp nền.

Nếu thiếu `Multi-Release: true`, các entry trong `META-INF/versions` không được xử lý như lớp thay thế của MRJAR.

## 2. Cấu trúc source set mẫu

Ta giữ module descriptor và lớp nền trong source set Java 9, rồi cung cấp một bản triển khai khác của cùng lớp cho Java 17:

```text
src/
  base/
    module-info.java
    com/acme/greetings/Greeting.java
  java17/
    com/acme/greetings/Greeting.java
build/
  base/
  versions/
    17/
  MANIFEST.MF
```

Nội dung `src/base/module-info.java`:

```java
module com.acme.greetings {
    exports com.acme.greetings;
}
```

Lớp nền `src/base/com/acme/greetings/Greeting.java` dùng API có từ Java 9:

```java
package com.acme.greetings;

import java.util.List;

public final class Greeting {
    private Greeting() {}

    public static void main(String[] args) {
        System.out.println(message());
    }

    public static String message() {
        return String.join(" ", List.of("Java", "9", "base"));
    }
}
```

Bản thay thế `src/java17/com/acme/greetings/Greeting.java` giữ nguyên tên lớp và API public, nhưng dùng text block của Java 17:

```java
package com.acme.greetings;

public final class Greeting {
    private Greeting() {}

    private static final String MESSAGE = """
            Java 17+ implementation
            """.strip();

    public static void main(String[] args) {
        System.out.println(message());
    }

    public static String message() {
        return MESSAGE;
    }
}
```

Hai source file cùng tạo ra binary name `com.acme.greetings.Greeting`. Khi chạy trên Java 9 đến Java 16, JVM dùng lớp nền. Từ Java 17 trở lên, JVM chọn lớp trong thư mục phiên bản 17. Module descriptor ở gốc vẫn xác định tên module và package được export.

## 3. Biên dịch từng source set bằng đúng release

Giả sử các thư mục output đã được tạo. Biên dịch module descriptor và mã nền:

```bash
javac --release 9 -d build/base src/base/module-info.java src/base/com/acme/greetings/Greeting.java
```

Biên dịch lớp thay thế:

```bash
javac --release 17 -d build/versions/17 src/java17/com/acme/greetings/Greeting.java
```

Hai lệnh dùng cùng một compiler nhưng có hai hợp đồng biên dịch khác nhau:

- Output trong `build/base` chỉ dùng cú pháp và API Java 9, phù hợp với mức nền của JAR.
- Output trong `build/versions/17` được phép dùng cú pháp và API Java 17. JVM cũ hơn Java 17 sẽ không chọn entry này.
- `module-info.class` được tạo cùng output nền, nên nằm ở gốc JAR sau khi đóng gói.
- Lớp thay thế phải giữ binary name và API public tương thích với lớp nền. Nếu source set thay thế cần các lớp dùng chung khác, cấu hình class path hoặc module path của bước biên dịch để compiler nhìn thấy đúng các kiểu đó.

Không biên dịch mọi source set bằng mặc định của JDK đang cài. Nếu dùng JDK 24 mà bỏ `--release 17`, lớp thay thế có thể được tạo với bytecode Java 24 và không chạy được trên Java 17.

## 4. Đóng gói thành Multi-Release JAR

Tạo file `build/MANIFEST.MF` với nội dung:

```text
Manifest-Version: 1.0
Multi-Release: true

```

Sau đó đóng gói output nền trước, rồi đến output phiên bản 17:

```bash
jar --create --file build/greetings.jar --manifest build/MANIFEST.MF -C build/base . --release 17 -C build/versions/17 .
```

Trong lệnh của JAR tool, `--release 17` đặt các file theo sau vào `META-INF/versions/17/`. Tùy chọn này chỉ sắp xếp entry khi đóng gói; nó không biên dịch source và khác với `javac --release 17`.

Các entry chính trong JAR sẽ có dạng:

```text
META-INF/MANIFEST.MF
module-info.class
com/acme/greetings/Greeting.class
META-INF/versions/17/com/acme/greetings/Greeting.class
```

Thứ tự tham số có ý nghĩa: `-C build/base .` thêm file nền ở gốc; `--release 17` áp dụng cho các file được thêm sau nó. Nếu đặt `--release 17` trước output nền, các file nền cũng có thể bị đưa nhầm vào thư mục phiên bản.

## 5. Kiểm tra module, cấu trúc JAR và hành vi runtime

Kiểm tra danh sách entry:

```bash
jar --list --file build/greetings.jar
```

Kiểm tra module descriptor ở gốc:

```bash
jar --describe-module --file build/greetings.jar
```

Kết quả cần nhận diện module `com.acme.greetings` và package `com.acme.greetings` được export.

Dùng JAR tool kiểm tra tính nhất quán của API public giữa các phiên bản:

```bash
jar --validate --file build/greetings.jar
```

Lệnh này giúp phát hiện khác biệt API public giữa các lớp ở những release khác nhau trong MRJAR. Nó không thay thế kiểm thử hành vi, kiểm thử tích hợp hoặc kiểm tra dependency.

Chạy module trên module path:

```bash
java --module-path build/greetings.jar --module com.acme.greetings/com.acme.greetings.Greeting
```

Kết quả mong đợi:

- Java 9 đến Java 16: `Java 9 base`.
- Java 17 trở lên: `Java 17+ implementation`.

Nên chạy kiểm thử trên từng runtime mà sản phẩm cam kết hỗ trợ. Việc biên dịch thành công bằng `--release` không chứng minh mọi dependency, cấu hình module hoặc hành vi lúc chạy đều tương thích.

## 6. Những lỗi thường gặp

1. **Chỉ dùng `-source` và `-target`:** mã nguồn vẫn có thể tham chiếu API mới hơn runtime đích. Dùng `--release` để khóa cả API Java SE.
2. **Dùng một release cho mọi source set:** lớp thay thế không thể dùng API mới nếu vẫn biên dịch bằng release nền; ngược lại, biên dịch nền bằng release quá mới làm mất khả năng chạy trên runtime tối thiểu.
3. **Quên `Multi-Release: true`:** JVM không chọn lớp trong `META-INF/versions` như một entry thay thế.
4. **Đặt sai đường dẫn hoặc thứ tự tham số của `jar`:** lớp thay thế phải nằm dưới `META-INF/versions/N`; `jar --release N` chỉ áp dụng cho các file theo sau.
5. **Thay đổi API public giữa các bản:** mã gọi có thể gặp lỗi liên kết như `NoSuchMethodError` tùy runtime. Giữ hợp đồng public tương thích và chạy `jar --validate`.
6. **Quên module descriptor:** một JAR có lớp trong `META-INF/versions` không tự trở thành named module. Với cấu hình Java 9 làm mức nền, descriptor phải được biên dịch và đặt ở gốc JAR.
7. **Cho rằng `--release` kiểm soát dependency:** tùy chọn này áp dụng cho source set đang biên dịch. Hãy kiểm tra riêng bytecode và yêu cầu runtime của các thư viện được đóng gói.

## 7. Quy tắc thiết kế khi phát hành

- Chọn một mức Java nền rõ ràng và biên dịch toàn bộ source set nền bằng `javac --release <base>`.
- Đặt `module-info.java` trong source set nền; giữ module name, exports và ranh giới module ổn định giữa các bản triển khai.
- Mỗi source set thay thế phải được biên dịch bằng release tương ứng với thư mục `META-INF/versions/N`.
- Giữ binary name và API public tương thích giữa lớp nền và lớp thay thế. Nếu thay đổi package export, service provider hoặc quyền reflective, phải rà soát lại module descriptor.
- Bật `Multi-Release: true`, kiểm tra entry bằng `jar --list`, descriptor bằng `jar --describe-module` và API bằng `jar --validate`.
- Chạy test trên từng runtime được hỗ trợ, bao gồm cả đường chạy module path và các tính năng chỉ có ở source set thay thế.

Khi tách đúng ba trách nhiệm — `--release` cho hợp đồng biên dịch, `module-info` cho ranh giới module và MRJAR cho lựa chọn entry theo runtime — một artifact có thể phục vụ nhiều phiên bản JVM mà vẫn giữ được cấu trúc module và API có thể kiểm tra.