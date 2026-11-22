# Đóng gói Multi-Release JAR bằng tùy chọn `jar --release`

## 1. Mục đích và nguyên lý

Multi-Release JAR (MRJAR) cho phép một tệp JAR chứa lớp dùng chung và các phiên bản lớp thay thế dành cho những phiên bản Java khác nhau. Nhờ đó, thư viện có thể giữ một implementation nền để chạy trên phiên bản Java tối thiểu đã chọn, đồng thời cung cấp implementation tận dụng API hoặc khả năng mới hơn cho runtime mới.

Tùy chọn `--release VERSION` của công cụ `jar` đặt tất cả tệp được đưa vào sau tùy chọn đó trong thư mục:

```text
META-INF/versions/VERSION/
```

Ví dụ, `--release 21` đưa các tệp tiếp theo vào `META-INF/versions/21/`. Khi chạy ứng dụng trên Java 9 trở lên, JVM nhìn JAR theo phiên bản runtime: nó chọn bản trong thư mục phiên bản cao nhất không vượt quá phiên bản Java đang chạy; nếu không có bản phù hợp thì dùng tệp ở gốc JAR.

Ví dụ với JAR có bản nền và bản Java 21:

- Runtime Java 17 dùng lớp ở gốc JAR.
- Runtime Java 21 dùng lớp trong `META-INF/versions/21/`.
- Runtime Java 25 cũng dùng bản Java 21 nếu JAR không có bản Java 25.

Cơ chế này hữu ích khi cần tối ưu thư viện cho runtime mới mà vẫn duy trì một baseline tương thích. Nó không tự động biến mọi JAR thành MRJAR: manifest phải có thuộc tính `Multi-Release: true`. Khi dùng `jar --release` để tạo JAR, công cụ tự thêm thuộc tính này vào manifest.

## 2. Phân biệt `jar --release` và `javac --release`

Hai tùy chọn cùng tên nhưng thực hiện hai việc khác nhau:

| Tùy chọn | Công cụ | Tác dụng |
|---|---|---|
| `javac --release 17` | Trình biên dịch | Biên dịch mã nguồn theo ngôn ngữ, API Java và định dạng bytecode của Java 17. |
| `jar --release 21` | Công cụ đóng gói | Đặt các tệp tiếp theo vào `META-INF/versions/21/` trong JAR. |

`jar --release` không biên dịch mã nguồn, không thay đổi bytecode và không bảo đảm lớp được biên dịch tương thích với phiên bản thư mục. Hãy biên dịch từng implementation bằng `javac --release` phù hợp trước khi đóng gói.

Các thư mục phiên bản của MRJAR bắt đầu từ Java 9. Vì vậy, giá trị dùng với `jar --release` phải là một phiên bản từ 9 trở lên. Phiên bản Java tối thiểu mà ứng dụng hỗ trợ vẫn phụ thuộc vào bytecode và API của các lớp ở gốc JAR.

## 3. Chuẩn bị các implementation

Ví dụ dưới đây dùng Java 17 làm baseline và cung cấp implementation riêng cho Java 21. Hai lớp có cùng tên đầy đủ `demo.RuntimeMessage` và cùng API công khai; phần thân phương thức trả về thông điệp khác nhau để dễ quan sát runtime đã chọn bản nào.

Cấu trúc thư mục:

```text
project/
├── src/
│   ├── base/
│   │   └── demo/
│   │       └── RuntimeMessage.java
│   └── java21/
│       └── demo/
│           └── RuntimeMessage.java
└── build/
```

**Implementation nền — `src/base/demo/RuntimeMessage.java`:**

```java
package demo;

public final class RuntimeMessage {
    private RuntimeMessage() {
    }

    public static String message() {
        return "Base implementation (Java 17+)";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

**Implementation dành cho Java 21 — `src/java21/demo/RuntimeMessage.java`:**

```java
package demo;

public final class RuntimeMessage {
    private RuntimeMessage() {
    }

    public static String message() {
        return "Java 21 implementation";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

Hai phiên bản phải giữ cùng đường dẫn lớp trong JAR: `demo/RuntimeMessage.class`. Khi đặt vào MRJAR, bản Java 21 sẽ nằm tại `META-INF/versions/21/demo/RuntimeMessage.class`.

## 4. Biên dịch và tạo Multi-Release JAR

Chạy các lệnh sau trong PowerShell từ thư mục `project`. Tạo thư mục đầu ra, biên dịch từng implementation, sau đó đóng gói theo đúng thứ tự:

```powershell
New-Item -ItemType Directory -Force -Path build/base, build/java21 | Out-Null

javac --release 17 -d build/base src/base/demo/RuntimeMessage.java
javac --release 21 -d build/java21 src/java21/demo/RuntimeMessage.java

jar --create --file build/runtime-message.jar -C build/base . --release 21 -C build/java21 .
```

Giải thích lệnh tạo JAR:

1. `--create` yêu cầu tạo archive mới.
2. `--file build/runtime-message.jar` đặt tên và đường dẫn JAR đầu ra.
3. `-C build/base .` chuyển vào thư mục `build/base` và thêm nội dung của thư mục đó vào gốc JAR.
4. `--release 21` chuyển vị trí đóng gói của các tệp tiếp theo sang `META-INF/versions/21/`.
5. `-C build/java21 .` thêm implementation Java 21 vào thư mục phiên bản tương ứng.

**Thứ tự tùy chọn có ý nghĩa.** Hãy thêm các lớp nền trước `--release 21`. Nếu đặt `--release 21` trước phần lớp nền, các tệp đó cũng sẽ bị đưa vào thư mục phiên bản và JAR có thể thiếu implementation ở gốc để runtime thấp hơn sử dụng.

## 5. Kiểm tra nội dung và chạy thử

Liệt kê các mục trong JAR:

```powershell
jar --list --file build/runtime-message.jar
```

Các đường dẫn quan trọng trong kết quả:

```text
demo/RuntimeMessage.class
META-INF/versions/21/demo/RuntimeMessage.class
META-INF/MANIFEST.MF
```

Manifest được công cụ tạo có thuộc tính chính:

```text
Multi-Release: true
```

Thuộc tính này cho runtime biết cần áp dụng cách nhìn MRJAR. Nếu tự tạo cấu trúc `META-INF/versions` bằng công cụ ZIP hoặc quy trình đóng gói khác, phải tự bảo đảm manifest có `Multi-Release: true`; chỉ tạo đúng thư mục là chưa đủ.

Chạy chương trình:

```powershell
java -cp build/runtime-message.jar demo.RuntimeMessage
```

Trên runtime Java 21 trở lên, kết quả của ví dụ là:

```text
Java 21 implementation
```

Trên runtime Java 17, lớp trong thư mục phiên bản 21 chưa được chọn nên kết quả là:

```text
Base implementation (Java 17+)
```

Có thể kiểm tra tính nhất quán API giữa các phiên bản bằng:

```powershell
jar --validate --file build/runtime-message.jar
```

Tùy chọn `--validate` kiểm tra API được xuất ra bởi MRJAR có nhất quán giữa các phiên bản hay không. Lệnh thành công với exit code 0; vẫn cần chạy test trên những runtime mà thư viện cam kết hỗ trợ, vì kiểm tra API không chứng minh hành vi của các implementation giống nhau.

## 6. Quy tắc thiết kế và lỗi thường gặp

- **Giữ implementation nền ở gốc JAR.** Đây là bản fallback khi runtime không có thư mục phiên bản phù hợp. Baseline thực tế phải được xác định từ phiên bản bytecode và API mà lớp nền sử dụng.
- **Giữ nguyên tên lớp và đường dẫn tương ứng.** Lớp thay thế phải nằm dưới cùng đường dẫn tương đối trong `META-INF/versions/VERSION/`; ví dụ `demo/RuntimeMessage.class` trở thành `META-INF/versions/21/demo/RuntimeMessage.class`.
- **Biên dịch theo đúng phiên bản mục tiêu.** Dùng `javac --release 17` cho lớp nền và `javac --release 21` cho implementation Java 21. Việc chỉ đổi tên thư mục thành `21` không làm bytecode trở thành bytecode Java 21.
- **Duy trì API tương thích.** Lớp thay thế thường nên giữ các constructor, phương thức và kiểu công khai mà mã gọi đã biên dịch dựa vào. API khác nhau có thể khiến ứng dụng chạy được trên runtime này nhưng lỗi liên kết trên runtime khác.
- **Kiểm tra manifest.** Nếu `Multi-Release: true` bị thiếu khi tự đóng gói, runtime sẽ không xử lý các entry phiên bản theo cơ chế MRJAR.
- **Không đưa tệp nền vào sai vị trí.** Mọi tệp theo sau `--release VERSION` được đặt trong thư mục phiên bản đó. Đặt sai thứ tự có thể làm mất fallback ở gốc.
- **Kiểm tra cả cấu trúc lẫn hành vi.** Dùng `jar --list` để xem đường dẫn, `jar --validate` để kiểm tra tính nhất quán API, rồi chạy test trên từng phiên bản Java mục tiêu.

Không cần tạo bản thay thế cho mọi phiên bản Java. Chỉ thêm thư mục phiên bản khi implementation thật sự cần API hoặc hành vi riêng; các phiên bản không có bản thay thế sẽ dùng bản phù hợp gần nhất hoặc bản nền ở gốc JAR.

## 7. Khi nào nên dùng

Dùng MRJAR khi một thư viện cần hỗ trợ nhiều phiên bản Java nhưng có thể tận dụng API hoặc implementation mới hơn trên runtime mới. Ví dụ, một lớp có thể dùng implementation nền cho Java 17 và implementation tối ưu cho Java 21 trở lên trong cùng một artifact.

Nếu sản phẩm chỉ hỗ trợ một phiên bản Java hoặc không có khác biệt implementation theo runtime, một JAR thông thường sẽ đơn giản hơn. MRJAR làm tăng số biến thể cần biên dịch, kiểm thử và duy trì; chỉ nên thêm các thư mục phiên bản đem lại lợi ích rõ ràng.
