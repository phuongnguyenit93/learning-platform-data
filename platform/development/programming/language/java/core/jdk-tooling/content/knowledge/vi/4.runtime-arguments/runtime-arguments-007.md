# Assertion option trong Java

## 1. Assertion là gì?

**Assertion** (khẳng định) là một câu lệnh dùng để kiểm tra giả định của lập trình viên về trạng thái hoặc logic bên trong chương trình. Assertion diễn đạt một điều kiện mà tại vị trí thực thi đó, lập trình viên tin rằng luôn phải đúng.

Trong Java, assertion được viết bằng từ khóa `assert`. Khi assertion được bật và điều kiện sai, JVM ném `AssertionError`. Khi assertion bị tắt, câu lệnh assertion không có tác dụng: cả biểu thức điều kiện lẫn biểu thức thông báo đều không được đánh giá.

Assertion thường hữu ích để:

- Kiểm tra invariant (bất biến) của một đối tượng hoặc cấu trúc dữ liệu.
- Xác nhận điều kiện nội bộ mà thuật toán cần duy trì.
- Kiểm tra giả định ở các nhánh logic mà lập trình viên cho rằng không thể xảy ra.
- Phát hiện lỗi lập trình sớm trong quá trình phát triển và kiểm thử.

Ví dụ, một thuật toán xử lý cây cân bằng có thể giả định rằng chiều cao hai nhánh không chênh lệch quá giới hạn. Assertion giúp phát hiện khi một thao tác cập nhật làm hỏng invariant đó.

Assertion là một phần của ngôn ngữ Java. **Assertion option** là tùy chọn lúc khởi chạy JVM để quyết định các câu lệnh `assert` nào được bật hoặc tắt.

## 2. Cú pháp assert

Java có hai dạng câu lệnh assertion:

```java
assert condition;
assert condition : detailMessage;
```

Trong đó:

- `condition` phải có kiểu `boolean` hoặc `Boolean`.
- `detailMessage` là một biểu thức có giá trị, dùng làm thông tin chẩn đoán khi điều kiện sai. Biểu thức này không được có kiểu `void`.
- Nếu điều kiện đúng, câu lệnh kết thúc bình thường.
- Nếu điều kiện sai và assertion đang bật, JVM ném `AssertionError`. Nếu có thông báo, giá trị của biểu thức thông báo được chuyển thành thông điệp chi tiết của lỗi.
- Nếu assertion đang tắt, không biểu thức nào trong câu lệnh được thực thi.

Ví dụ:

```java
int itemCount = 12;
assert itemCount >= 0;
assert itemCount <= 100 : "itemCount is out of expected range: " + itemCount;
```

Dạng có thông báo đặc biệt hữu ích khi cần biết giá trị nào đã khiến giả định thất bại. Thông báo được đánh giá khi điều kiện sai, vì vậy không cần xây dựng chuỗi chẩn đoán khi điều kiện đúng.

### 2.1. Assertion thất bại tạo ra AssertionError

`AssertionError` là một lớp con của `Error`, không phải lớp con của `Exception`. Nó biểu thị rằng một giả định trong chương trình đã không còn đúng.

Ví dụ:

```java
int remainingBytes = 4;
assert remainingBytes == 0 : "Unexpected bytes remaining: " + remainingBytes;
```

Nếu assertion được bật, chương trình ném `AssertionError` với thông tin chẩn đoán tương ứng. Stack trace thường chỉ ra tệp và dòng mã chứa assertion thất bại.

Không nên dùng assertion như một cơ chế xử lý lỗi thông thường hoặc bắt `AssertionError` để tiếp tục như thể dữ liệu đầu vào không hợp lệ là tình huống có thể phục hồi. Assertion thường chỉ ra lỗi logic hoặc vi phạm giả định nội bộ cần được điều tra.

## 3. Assertion mặc định bị tắt

Theo mặc định, các câu lệnh `assert` trong Java bị tắt khi ứng dụng khởi chạy. Vì vậy, chỉ viết:

```java
assert balance >= 0;
```

không có nghĩa điều kiện sẽ luôn được kiểm tra khi chạy ứng dụng.

Muốn kiểm tra assertion, phải bật nó bằng tùy chọn của Java launcher. Việc bật hoặc tắt này diễn ra lúc khởi chạy JVM, không phải bằng một lệnh trong mã nguồn.

Điều này cho phép đội phát triển bật kiểm tra trong môi trường development hoặc test, trong khi lựa chọn bật hay tắt ở môi trường khác tùy thuộc nhu cầu vận hành.

## 4. Các assertion option quan trọng

Các tùy chọn phổ biến của lệnh `java`:

| Tùy chọn | Ý nghĩa |
|---|---|
| `-ea` hoặc `-enableassertions` | Bật assertion cho các lớp ứng dụng; dạng không có đối số không áp dụng cho system classes |
| `-da` hoặc `-disableassertions` | Tắt assertion cho các lớp ứng dụng; dạng không có đối số không áp dụng cho system classes |
| `-ea:com.example...` | Bật assertion trong package `com.example` và các subpackage |
| `-da:com.example...` | Tắt assertion trong package `com.example` và các subpackage |
| `-ea:com.example.Checks` | Bật assertion trong đúng lớp `com.example.Checks` |
| `-da:com.example.LegacyParser` | Tắt assertion trong đúng lớp `com.example.LegacyParser` |
| `-esa` hoặc `-enablesystemassertions` | Bật assertion trong các system classes |
| `-dsa` hoặc `-disablesystemassertions` | Tắt assertion trong các system classes |

Các điểm cần nhớ:

- `-ea` là viết tắt của `-enableassertions`.
- `-da` là viết tắt của `-disableassertions`.
- Với dạng không có đối số, `-ea` bật assertion trong các lớp ứng dụng; system classes cần tùy chọn riêng `-esa`.
- `-da` không có đối số tắt assertion trong các lớp ứng dụng; `-dsa` điều khiển assertion của system classes.
- Ba dấu chấm `...` ở cuối tên package là cú pháp chỉ package cùng mọi package con. Đây không phải ký tự đại diện `*`.
- Tên lớp phải là tên đầy đủ (fully qualified class name), gồm package nếu lớp có package.
- Có thể kết hợp nhiều tùy chọn trong cùng một lệnh. JVM xử lý chúng theo thứ tự trước khi nạp lớp, nên một tùy chọn cụ thể xuất hiện sau có thể ghi đè lựa chọn trước đó cho phạm vi trùng nhau.

### 4.1. Bật assertion cho toàn bộ lớp ứng dụng

```bash
java -ea -cp out com.example.Main
```

Lệnh này bật assertion trong các lớp ứng dụng được chạy trong JVM. System classes không được bật chỉ bởi dạng `-ea` không có đối số.

Nếu chạy ứng dụng từ JAR:

```bash
java -ea -jar app.jar
```

### 4.2. Bật assertion cho một package

```bash
java -ea:com.example... -cp out com.example.Main
```

Phạm vi này bao gồm các lớp trong package `com.example` và các package con như `com.example.service` hoặc `com.example.internal`.

Nếu chỉ muốn bật trong một lớp:

```bash
java -ea:com.example.Checks -cp out com.example.Main
```

### 4.3. Bật theo package rồi tắt một lớp cụ thể

Có thể phối hợp `-ea` và `-da` để tạo phạm vi chi tiết:

```bash
java -ea:com.example... -da:com.example.LegacyParser -cp out com.example.Main
```

Trong ví dụ này, assertion được bật cho package `com.example` và các package con, sau đó bị tắt riêng cho lớp `com.example.LegacyParser`. Thứ tự tùy chọn có ý nghĩa vì JVM xử lý chúng theo thứ tự trước khi nạp các lớp.

### 4.4. Bật assertion trong system classes

```bash
java -esa -jar app.jar
```

`-esa` bật assertion trong các system classes. Đây thường là tùy chọn phục vụ chẩn đoán hoặc phát triển JVM và thư viện nền tảng; ứng dụng thông thường thường chỉ cần `-ea` cho các lớp của mình.

## 5. Vị trí đặt assertion option trong lệnh java

Assertion option là **JVM option**, vì vậy phải đặt trước tên lớp chính hoặc trước `-jar`.

Đúng:

```bash
java -ea -cp out com.example.Main
java -ea -jar app.jar
```

Sai về vị trí:

```bash
java -cp out com.example.Main -ea
```

Trong lệnh cuối, `-ea` nằm sau tên lớp chính nên được chuyển vào `args[]` của phương thức `main` như một đối số của ứng dụng. Nó không bật assertion cho JVM.

Cũng không đặt `-ea` vào lệnh biên dịch `javac`. Assertion option điều khiển runtime; compiler chỉ cần biên dịch mã Java có từ khóa `assert` như bình thường.

Khi chạy bằng module, assertion option cũng được đặt trước tùy chọn xác định module chính, ví dụ:

```bash
java -ea -m my.module/com.example.Main
```

## 6. Ví dụ thực hành: quan sát sự khác nhau giữa bật và tắt assertion

Tạo tệp `src/com/example/AssertionDemo.java`:

```java
package com.example;

public class AssertionDemo {
    public static void main(String[] args) {
        int itemCount = -3;

        assert itemCount >= 0
                : "itemCount must be non-negative, actual=" + itemCount;

        System.out.println("itemCount=" + itemCount);
    }
}
```

Biên dịch chương trình:

```bash
javac -d out src/com/example/AssertionDemo.java
```

### 6.1. Chạy khi assertion đang tắt

```bash
java -cp out com.example.AssertionDemo
```

Kết quả:

```text
itemCount=-3
```

Điều kiện `itemCount >= 0` không được đánh giá vì assertion mặc định bị tắt. Chương trình tiếp tục đến câu lệnh `println`.

### 6.2. Chạy khi assertion được bật

```bash
java -ea -cp out com.example.AssertionDemo
```

Kết quả chính:

```text
Exception in thread "main" java.lang.AssertionError: itemCount must be non-negative, actual=-3
```

JVM ném `AssertionError` và dừng luồng thực thi hiện tại nếu lỗi không được xử lý. Stack trace đầy đủ còn chứa vị trí dòng trong tệp Java.

### 6.3. Thử với điều kiện đúng

Đổi giá trị `itemCount` thành `3` rồi chạy lại với `-ea`:

```text
itemCount=3
```

Khi điều kiện đúng, assertion được đánh giá và chương trình tiếp tục bình thường.

## 7. Dùng assertion để kiểm tra invariant và giả định nội bộ

Assertion phát huy tác dụng khi kiểm tra những điều mà chương trình cần duy trì bên trong.

Ví dụ, một lớp quản lý khoảng số có invariant là giá trị đầu không lớn hơn giá trị cuối:

```java
public class NumberRange {
    private int start;
    private int end;

    public NumberRange(int start, int end) {
        if (start > end) {
            throw new IllegalArgumentException("start must be <= end");
        }

        this.start = start;
        this.end = end;
        assert this.start <= this.end : "Invalid range state";
    }

    public int size() {
        assert start <= end : "Range invariant was broken";
        return end - start;
    }
}
```

Constructor dùng `IllegalArgumentException` để từ chối dữ liệu đầu vào không hợp lệ. Assertion sau khi gán trường kiểm tra invariant nội bộ mà lớp cần duy trì. Phương thức `size` kiểm tra lại giả định trước khi tính toán.

Một số trường hợp phù hợp:

- Kiểm tra trạng thái nội bộ sau một thao tác cập nhật.
- Kiểm tra kết quả trung gian của thuật toán.
- Kiểm tra quan hệ giữa các biến mà logic chương trình phải bảo đảm.
- Kiểm tra nhánh mã được cho là không thể đi tới.

Ví dụ nhánh không mong đợi:

```java
switch (status) {
    case READY -> start();
    case STOPPED -> stop();
    case PAUSED -> resume();
    default -> {
        assert false : "Unexpected status: " + status;
        throw new IllegalStateException("Unsupported status: " + status);
    }
}
```

Ở đây, exception vẫn được ném khi assertion bị tắt, nên chương trình không âm thầm tiếp tục với trạng thái không được hỗ trợ. Assertion bổ sung thông tin chẩn đoán khi bật.

## 8. Những điều không nên làm với assert

### 8.1. Không dùng assert để kiểm tra đầu vào của public method

Không nên viết:

```java
public void transfer(Account target, int amount) {
    assert target != null;
    assert amount > 0;

    // Thực hiện chuyển tiền
}
```

Nếu assertion bị tắt, các điều kiện trên không được kiểm tra. Hợp đồng của public method vì vậy không được bảo đảm.

Hãy dùng exception phù hợp:

```java
import java.util.Objects;

public void transfer(Account target, int amount) {
    Objects.requireNonNull(target, "target must not be null");

    if (amount <= 0) {
        throw new IllegalArgumentException("amount must be positive");
    }

    // Thực hiện chuyển tiền
}
```

Kiểm tra đầu vào công khai phải luôn hoạt động, bất kể JVM có bật assertion hay không.

### 8.2. Không đặt side effect trong biểu thức assertion

Không nên viết:

```java
assert queue.remove(item);
```

Khi assertion bật, phần tử bị xóa khỏi queue. Khi assertion tắt, lệnh xóa không xảy ra. Chương trình vì vậy có hành vi khác nhau tùy JVM option.

Hãy thực hiện thao tác trước rồi kiểm tra kết quả:

```java
boolean removed = queue.remove(item);
assert removed : "Expected item to be present in queue";
```

Thao tác xóa luôn xảy ra; assertion chỉ kiểm tra giả định về kết quả.

### 8.3. Không dùng assert để bảo vệ bảo mật

Không dùng assertion làm lớp kiểm tra duy nhất cho quyền truy cập, xác thực, dữ liệu không tin cậy hoặc điều kiện an toàn. Các kiểm tra bảo mật phải luôn được thực hiện và phải có hành vi rõ ràng khi thất bại.

### 8.4. Không dựa vào assert để tạo dữ liệu cần thiết

Không nên đặt lời gọi khởi tạo hoặc cập nhật trạng thái trong điều kiện assertion. Vì câu lệnh có thể bị bỏ qua hoàn toàn, dữ liệu cần thiết có thể không được tạo hoặc cập nhật.

### 8.5. Không nhầm AssertionError với exception nghiệp vụ

`AssertionError` thường biểu thị lỗi trong giả định của lập trình viên. Những tình huống nghiệp vụ như số dư không đủ, dữ liệu đầu vào sai hoặc tài nguyên không tồn tại nên được biểu diễn bằng exception phù hợp hoặc kết quả nghiệp vụ rõ ràng.

## 9. Assertion option trong IDE và công cụ build

Khi chạy Java từ IDE hoặc build tool, JVM không nhất thiết được khởi chạy bằng đúng câu lệnh bạn gõ trong terminal. Cần đặt assertion option vào phần cấu hình dành cho JVM.

| Công cụ | Vị trí thường dùng |
|---|---|
| IntelliJ IDEA | Run/Debug Configuration → VM options |
| Eclipse | Run Configurations → Arguments → VM arguments |
| Visual Studio Code | Trường `vmArgs` trong cấu hình chạy Java |
| Lệnh `java` trực tiếp | Đặt `-ea` trước tên lớp chính hoặc `-jar` |
| Maven/Gradle test runner | Cấu hình JVM của tiến trình test theo hướng dẫn của plugin hoặc task đang dùng |

Ví dụ cấu hình chạy trong VS Code có thể dùng trường `vmArgs`:

```json
{
  "type": "java",
  "name": "Run with assertions",
  "request": "launch",
  "mainClass": "com.example.AssertionDemo",
  "vmArgs": "-ea"
}
```

Nếu đặt `-ea` trong program arguments thay vì VM options, assertion sẽ không được bật. Khi debug một lỗi chỉ xuất hiện trong chế độ assertion, hãy kiểm tra cấu hình chạy của IDE và tiến trình test riêng biệt.

## 10. Java assert và JUnit Assertions khác nhau thế nào?

Hai khái niệm này có tên gần giống nhau nhưng cơ chế khác nhau:

| Tiêu chí | Java `assert` | JUnit Assertions |
|---|---|---|
| Bản chất | Từ khóa và câu lệnh của ngôn ngữ Java | Các phương thức của thư viện kiểm thử |
| Bật/tắt | Phụ thuộc assertion status của JVM | Được gọi như phương thức kiểm thử bình thường |
| Khi thất bại | Ném `AssertionError` | Test framework ghi nhận test thất bại, thường qua assertion error |
| Phạm vi | Giả định và invariant trong mã chương trình | Kiểm tra kết quả mong đợi của test |
| Tắt assertion JVM | Câu lệnh Java `assert` không thực hiện | Các lời gọi JUnit như `assertEquals` vẫn hoạt động |

Ví dụ JUnit:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(5, 2 + 3);
    }
}
```

`assertEquals` là phương thức của JUnit, không phải câu lệnh `assert` của Java. Nó vẫn được thực thi theo cơ chế của test framework, không phụ thuộc vào việc có truyền `-ea` hay không.

Trong dự án thực tế, dùng JUnit Assertions để xác minh kết quả test; dùng Java `assert` để diễn đạt các giả định nội bộ của chương trình.

## 11. Lỗi thường gặp khi dùng assertion option

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Assertion sai nhưng chương trình vẫn chạy tiếp | JVM chưa bật assertion | Thêm `-ea` vào VM options |
| Đặt `-ea` nhưng không có tác dụng | Đặt sau tên lớp chính hoặc trong program arguments | Chuyển `-ea` lên trước tên lớp hoặc `-jar` |
| Lớp trong package không kiểm tra assertion | Phạm vi option chưa bao gồm package hoặc class đó | Dùng `-ea:com.example...` hoặc tên lớp đầy đủ |
| Một lớp không kiểm tra trong khi package đã bật | Có tùy chọn `-da` cụ thể ghi đè phạm vi rộng hơn | Kiểm tra thứ tự các option và phạm vi áp dụng |
| Assertion chạy trong terminal nhưng không chạy trong IDE | IDE dùng cấu hình JVM riêng | Kiểm tra VM options của Run/Debug Configuration |
| Hành vi ứng dụng thay đổi khi bật assertion | Biểu thức assertion có side effect | Đưa thao tác có tác dụng phụ ra ngoài câu lệnh assert |
| Public method bỏ lọt dữ liệu sai | Dùng assert để kiểm tra tham số công khai | Dùng exception hoặc validation luôn được thực thi |

Có thể kiểm tra nhanh bằng cách tạo một assertion chắc chắn sai:

```java
assert false : "Assertion option check";
```

Sau đó chạy chương trình một lần không có `-ea` và một lần có `-ea`. Nếu cấu hình đúng, lần bật assertion sẽ ném `AssertionError`.

## 12. Quy trình thực hành và kiểm tra

Khi cần xác minh assertion option trong một dự án:

1. Tìm các câu lệnh `assert` trong mã nguồn và xác định chúng kiểm tra invariant hay dữ liệu đầu vào.
2. Kiểm tra cách ứng dụng được khởi chạy: terminal, IDE, Maven, Gradle hay container.
3. Đặt `-ea` vào JVM options của đúng tiến trình.
4. Nếu cần phạm vi nhỏ, dùng `-ea:package...` hoặc `-ea:fully.qualified.Class`.
5. Tạo một tình huống làm điều kiện sai để xác nhận `AssertionError` xuất hiện.
6. Chạy lại khi không bật assertion để hiểu những câu lệnh nào bị bỏ qua.
7. Loại bỏ side effect khỏi các biểu thức assertion và dùng exception cho các điều kiện bắt buộc.
8. Ghi lại cấu hình chạy trong tài liệu hoặc cấu hình nhóm nếu assertion là một phần của quy trình kiểm thử.

## 13. Tổng kết

Assertion là công cụ kiểm tra giả định và invariant trong chương trình Java. Câu lệnh `assert` có thể bị tắt khi chạy, vì vậy cần hiểu rõ cách điều khiển nó bằng assertion option:

- `-ea` bật assertion trong các lớp ứng dụng.
- `-da` tắt assertion trong các lớp ứng dụng.
- `-ea:package...` hoặc `-ea:ClassName` giới hạn phạm vi bật.
- `-da:package...` hoặc `-da:ClassName` giới hạn phạm vi tắt.
- `-esa` và `-dsa` điều khiển assertion trong system classes.
- JVM option phải nằm trước tên lớp chính hoặc `-jar`.
- Không dùng assertion cho side effect, kiểm tra đầu vào public method hoặc bảo vệ bảo mật.
- Java `assert` khác với các phương thức assertion của JUnit.

Khi được dùng đúng mục đích, assertion giúp phát hiện giả định sai trong quá trình phát triển và kiểm thử, đồng thời cung cấp thông tin hữu ích để tìm nguyên nhân lỗi logic.
