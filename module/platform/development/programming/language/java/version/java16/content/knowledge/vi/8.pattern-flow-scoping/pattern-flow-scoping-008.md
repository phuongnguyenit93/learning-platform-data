# Phạm vi pattern trong vòng lặp và ảnh hưởng của break

Pattern matching cho `instanceof` được hoàn thiện trong Java 16. Khi kiểm tra một giá trị, ta có thể khai báo biến pattern ngay trong điều kiện:

```java
while (value instanceof String text) {
    System.out.println(text.length());
    value = readNextValue();
}
```

Biến `text` được sử dụng trong thân `while` vì thân vòng lặp chỉ chạy khi điều kiện đúng và pattern đã khớp. Tuy nhiên, phạm vi pattern variable trong vòng lặp còn phụ thuộc vào cách vòng lặp kết thúc. Đặc biệt, `break` có thể rời vòng lặp trước khi điều kiện được kiểm tra lại, khiến compiler không thể chứng minh pattern đã khớp ở phần mã sau vòng lặp.

Trong module Java 16, pattern matching cho `instanceof` là cải tiến ngôn ngữ vẫn hữu ích trong Java hiện đại, bên cạnh `record` và các API Stream. Bài này tập trung vào phạm vi pattern trong `while`, `for`, `do-while`, cùng ảnh hưởng của `break` và `continue`. Các ví dụ sử dụng cú pháp đã được chuẩn hóa, không cần preview feature.

## 1. Pattern variable trong điều kiện `while`

Với điều kiện pattern dương, biến pattern nằm trong thân vòng lặp:

```java
static void printStrings(Object value) {
    while (value instanceof String text) {
        System.out.println("Độ dài: " + text.length());
        value = readNextValue();
    }
}

static Object readNextValue() {
    return null;
}
```

Java đánh giá điều kiện trước mỗi lần thực hiện thân vòng lặp. Nếu `value` là `String`, pattern khớp và `text` được tạo cho lần lặp đó. Nếu `value` không phải `String` hoặc là `null`, điều kiện sai và thân vòng lặp bị bỏ qua.

Biến `text` không tự động có mặt sau vòng lặp này. Vòng lặp có thể kết thúc khi điều kiện `value instanceof String text` sai; đó chính là trường hợp pattern chưa khớp.

## 2. Điều kiện phủ định có thể đưa pattern variable ra sau vòng lặp

Một cách viết hữu ích là lặp khi giá trị chưa thuộc kiểu mong muốn:

```java
static void waitForText(Object value) {
    while (!(value instanceof String text)) {
        value = readNextValue();
    }

    // Vòng lặp kết thúc bình thường khi pattern đã khớp.
    System.out.println(text.strip());
}
```

Điều kiện `!(value instanceof String text)` đúng khi `value` không phải `String` hoặc là `null`. Khi đó, thân vòng lặp chạy để lấy giá trị tiếp theo. Vòng lặp kết thúc bình thường khi điều kiện sai; điều kiện sai đồng nghĩa với `value instanceof String text` đúng.

Vì vậy, nếu luồng thực thi đi qua vòng lặp bằng cách kiểm tra điều kiện thành `false`, compiler có thể chứng minh `text` đã được khớp và cho phép sử dụng biến sau vòng lặp.

Mẫu này hữu ích khi cần đọc lại dữ liệu, chờ một trạng thái hoặc tiếp tục xử lý cho đến khi nhận được một giá trị đúng kiểu. Trong ứng dụng thực tế, cần có giới hạn thử lại hoặc cơ chế dừng phù hợp để tránh vòng lặp không kết thúc nếu giá trị không bao giờ đạt yêu cầu.

## 3. `break` có thể làm mất bảo đảm sau vòng lặp

`break` kết thúc vòng lặp ngay lập tức và bỏ qua lần kiểm tra điều kiện tiếp theo. Với vòng lặp có điều kiện phủ định, thân vòng lặp đang chạy chính là trường hợp pattern chưa khớp. Vì thế, nếu `break` có thể thoát vòng lặp trong trạng thái đó, phần mã sau vòng lặp không thể giả định biến pattern đã được tạo.

```java
static void waitForText(Object value, boolean stop) {
    while (!(value instanceof String text)) {
        if (stop) {
            break;
        }
        value = readNextValue();
    }

    // Lỗi biên dịch: break có thể thoát khi value chưa phải String.
    System.out.println(text.strip());
}
```

Có hai cách thoát khỏi vòng lặp:

- Điều kiện được đánh giá lại và trở thành `false`: pattern đã khớp.
- `stop` là `true` và `break` chạy: vòng lặp kết thúc dù pattern chưa khớp.

Vì tồn tại đường đi thứ hai, compiler không thể đảm bảo `text` đã được gán sau vòng lặp. Đây là ảnh hưởng quan trọng của `break` đối với flow scoping.

## 4. Dùng `return` hoặc `throw` nếu trường hợp dừng không thể tiếp tục

Nếu yêu cầu dừng đồng nghĩa với việc phương thức không thể xử lý tiếp, hãy kết thúc phương thức thay vì chỉ thoát vòng lặp:

```java
static void waitForText(Object value, boolean stop) {
    while (!(value instanceof String text)) {
        if (stop) {
            return;
        }
        value = readNextValue();
    }

    System.out.println(text.strip());
}
```

Khi `stop` là `true`, `return` kết thúc phương thức. Đường đi đó không đến câu lệnh sử dụng `text`. Nếu phương thức tiếp tục sau vòng lặp, chỉ có thể là do điều kiện đã trở thành `false`, tức pattern đã khớp.

Nếu việc không nhận được chuỗi là lỗi nghiệp vụ, có thể ném ngoại lệ:

```java
static String requireText(Object value, boolean stop) {
    while (!(value instanceof String text)) {
        if (stop) {
            throw new IllegalStateException("Không nhận được dữ liệu dạng chuỗi");
        }
        value = readNextValue();
    }

    return text.strip();
}
```

`return` và `throw` kết thúc đường đi không khớp, nên không tạo ra lối thoát khỏi vòng lặp rồi tiếp tục sử dụng biến chưa được khớp.

## 5. `continue` khác `break` như thế nào?

`continue` bỏ qua phần còn lại của thân vòng lặp hiện tại và chuyển sang lần kiểm tra tiếp theo. Nó không thoát khỏi vòng lặp. Vì vậy, với điều kiện phủ định, `continue` không tạo ra đường đi đến sau vòng lặp khi pattern chưa khớp:

```java
static void waitForText(Object value) {
    while (!(value instanceof String text)) {
        if (shouldRetry(value)) {
            continue;
        }

        value = readNextValue();
    }

    System.out.println(text.strip());
}

static boolean shouldRetry(Object value) {
    return false;
}
```

Khi `continue` chạy, Java quay lại đánh giá điều kiện `while`. Chương trình chỉ rời vòng lặp bình thường khi điều kiện phủ định sai, tức pattern đã khớp.

| Câu lệnh trong thân vòng lặp | Tác động đến luồng điều khiển | Ảnh hưởng đến biến sau vòng lặp |
|---|---|---|
| `continue` | Chuyển sang lần kiểm tra điều kiện tiếp theo | Không tạo đường thoát sớm khỏi vòng lặp. |
| `break` | Thoát vòng lặp ngay, không kiểm tra điều kiện lần nữa | Có thể tạo đường thoát khi pattern chưa khớp. |
| `return` | Kết thúc phương thức | Đường đi đó không đến mã sau vòng lặp. |
| `throw` | Ném ngoại lệ | Đường đi đó không tiếp tục bình thường sau vòng lặp. |

## 6. Phạm vi pattern trong vòng lặp `for`

Với vòng lặp `for` có điều kiện, pattern variable được dùng trong thân khi điều kiện đúng:

```java
static void printTextValues(Object value) {
    for (; value instanceof String text; value = readNextValue()) {
        System.out.println(text.toUpperCase());
    }
}
```

Mỗi lần lặp, Java đánh giá điều kiện. Nếu pattern khớp, thân vòng lặp chạy và `text` có thể được dùng trong thân. Khi điều kiện sai, vòng lặp kết thúc; trong ví dụ này, pattern không khớp ở lần kiểm tra cuối nên không thể sử dụng `text` sau vòng lặp.

Tương tự `while`, điều kiện phủ định cho phép pattern được xác nhận khi vòng lặp kết thúc bình thường:

```java
static void findText(Object value) {
    for (; !(value instanceof String text); value = readNextValue()) {
        // Tiếp tục tìm giá trị có kiểu String.
    }

    System.out.println(text.length());
}
```

Vòng lặp chỉ kết thúc qua điều kiện sai khi `value` đã là `String`. Nếu thêm một `break` có thể chạy khi điều kiện phủ định còn đúng, biến `text` sẽ không được bảo đảm ở câu lệnh sau vòng lặp.

## 7. Vòng lặp `do-while` đánh giá điều kiện sau thân

Khác với `while` và `for`, vòng lặp `do-while` thực hiện thân trước rồi mới đánh giá điều kiện:

```java
static void readUntilText(Object value) {
    do {
        value = readNextValue();
    } while (!(value instanceof String text));
}
```

Biến pattern `text` được khai báo trong điều kiện ở cuối vòng lặp, nên không thể dùng trong thân `do`. Thân chạy trước khi điều kiện này được đánh giá. Các quy tắc short-circuit vẫn áp dụng bên trong biểu thức điều kiện; ví dụ, nếu điều kiện có `&&` hoặc `||`, biến pattern chỉ dùng được ở những vế mà kết quả trước đó chứng minh pattern đã khớp.

Khi đọc mã `do-while`, cần chú ý mọi đường thoát. `break` trong thân có thể rời vòng lặp trước khi điều kiện cuối được đánh giá. Do đó, không thể dựa vào điều kiện cuối để kết luận pattern đã khớp trên đường thoát bằng `break`.

## 8. `break` chỉ ảnh hưởng vòng lặp mà nó nhắm đến

Một câu lệnh `break` không có nhãn thoát khỏi cấu trúc `switch` hoặc vòng lặp gần nhất có thể nhận `break`. Vì vậy, không phải mọi `break` xuất hiện bên trong vòng lặp đều thoát khỏi vòng lặp đang khai báo pattern.

Ví dụ, `break` trong vòng lặp lồng chỉ thoát vòng lặp bên trong:

```java
static void findText(Object value) {
    while (!(value instanceof String text)) {
        for (int i = 0; i < 3; i++) {
            if (shouldStopInnerLoop(i)) {
                break; // Chỉ thoát vòng for bên trong.
            }
        }

        value = readNextValue();
    }

    System.out.println(text.strip());
}

static boolean shouldStopInnerLoop(int index) {
    return index == 1;
}
```

Vòng `while` bên ngoài vẫn tiếp tục và điều kiện của nó được kiểm tra lại. Vì `break` không thoát vòng `while`, nó không tạo đường đi bỏ qua lần kiểm tra pattern cuối cùng.

Ngược lại, một `break` có nhãn nhắm đến vòng ngoài có thể thoát vòng ngoài ngay cả khi điều kiện phủ định vẫn đúng:

```java
static void findText(Object value, boolean stop) {
    search: while (!(value instanceof String text)) {
        for (int i = 0; i < 3; i++) {
            if (stop) {
                break search; // Thoát vòng while được gắn nhãn.
            }
        }

        value = readNextValue();
    }

    // Không thể dùng text: break search có thể thoát khi pattern chưa khớp.
}
```

Khi phân tích phạm vi, hãy xác định chính xác `break` đang nhắm đến vòng lặp nào. Chỉ break có thể thoát khỏi vòng lặp liên quan mới tạo đường thoát sớm cần xét ở phần mã sau vòng lặp đó.

## 9. Cách xử lý khi cần thoát vòng lặp nhưng vẫn phải dùng dữ liệu

Nếu nghiệp vụ yêu cầu thoát vòng lặp bằng `break` rồi tiếp tục xử lý, hãy kiểm tra lại kiểu sau vòng lặp bằng một pattern mới:

```java
static void findText(Object value, boolean stop) {
    while (!(value instanceof String)) {
        if (stop) {
            break;
        }
        value = readNextValue();
    }

    if (!(value instanceof String text)) {
        return;
    }

    System.out.println(text.strip());
}
```

Ở đây, `break` có thể đưa chương trình ra khỏi vòng lặp khi `value` chưa phải `String`. Guard clause thứ hai kiểm tra lại giá trị thực tế và chỉ cho phép phần xử lý tiếp tục khi pattern mới đã khớp.

Nếu muốn báo lỗi thay vì bỏ qua trường hợp sai kiểu, thay `return` bằng `throw` phù hợp với hợp đồng phương thức. Cách này làm rõ rằng sau một lối thoát bằng `break`, cần xác nhận lại điều kiện trước khi dùng dữ liệu.

## 10. Bảng tổng hợp các tình huống

| Cấu trúc | Biến pattern dùng trong thân? | Có thể dùng sau vòng lặp? |
|---|---|---|
| `while (value instanceof String text)` | Có, khi điều kiện đúng | Không, vì vòng lặp có thể kết thúc khi pattern sai. |
| `while (!(value instanceof String text)) { ... }` không có `break` thoát vòng | Không, thân chạy khi pattern chưa khớp | Có, khi vòng lặp kết thúc bình thường do điều kiện sai. |
| `while (!(value instanceof String text)) { break; }` | Không | Không, vì break có thể thoát khi pattern sai. |
| `while (!(value instanceof String text)) { continue; }` | Không | Có về mặt flow scoping nếu không có lối thoát khác; continue quay lại kiểm tra điều kiện. |
| `for (; !(value instanceof String text); ) { ... }` không có `break` thoát vòng | Không, thân chạy khi pattern chưa khớp | Có khi kết thúc bình thường do điều kiện sai. |
| `do { ... } while (!(value instanceof String text));` | Không, điều kiện chạy sau thân | Điều kiện cuối chỉ chứng minh pattern trên đường thoát do điều kiện; break trong thân có thể bỏ qua kiểm tra đó. |

## 11. Cách áp dụng trong mã Java hiện đại

- Đặt pattern trong điều kiện `while` hoặc `for` khi thân vòng lặp chỉ cần chạy sau khi giá trị đã khớp kiểu.
- Dùng điều kiện phủ định khi muốn lặp cho đến khi nhận được giá trị đúng kiểu rồi xử lý biến pattern sau vòng lặp.
- Trước khi dùng biến pattern sau vòng lặp, kiểm tra mọi `break` có thể thoát vòng đó, bao gồm cả `break` có nhãn.
- Dùng `continue` khi cần thử lại điều kiện; nó không rời vòng lặp như `break`.
- Nếu vẫn cần `break` để thoát sớm, hãy kiểm tra lại kiểu sau vòng lặp bằng một pattern mới.
- Với `do-while`, nhớ rằng thân chạy trước điều kiện; biến pattern khai báo trong điều kiện không dùng được trong thân.

Flow scoping trong vòng lặp phụ thuộc vào kết quả điều kiện và mọi đường thoát khỏi vòng lặp. Vòng lặp kết thúc bình thường khi điều kiện phủ định trở thành sai có thể chứng minh pattern đã khớp. `break` có thể bỏ qua lần kiểm tra đó, vì vậy cần phân tích đúng đích của break hoặc kiểm tra lại kiểu trước khi dùng dữ liệu sau vòng lặp.
