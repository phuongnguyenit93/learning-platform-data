# Quy tắc mọi đường đi bình thường phải tạo kết quả trong `switch` expression (Java 14)

## 1. Mô hình cần nắm

Khi sử dụng `switch` dưới dạng **biểu thức** (switch expression), Java cần một giá trị để hoàn tất phép gán, biểu thức `return` hoặc đối số gọi phương thức. Ví dụ:

```java
int day = 2;
String label = switch (day) {
    case 1 -> "Thứ hai";
    case 2 -> "Thứ ba";
    default -> "Ngày khác";
};
```

Đây là tính năng được chuẩn hóa ở Java 14 và **tiếp tục được sử dụng trong các phiên bản Java hiện đại**. Quy tắc trung tâm là: **khi đánh giá `switch` expression kết thúc bình thường, nó phải có giá trị**. Một nhánh được chọn không thể chạy tới cuối khối rồi ra ngoài mà không tạo giá trị.

Có hai cách rời nhánh hợp lệ:

- **Trả kết quả cho biểu thức `switch`:** biểu thức trực tiếp sau `->` hoặc câu lệnh `yield value;` trong khối.
- **Ném ngoại lệ:** `throw` kết thúc đột ngột; lần đánh giá đó không có giá trị để trả về.

Trong ngôn ngữ đặc tả, `case ... -> { ... }` là **switch rule block**. Khối loại này **không được có khả năng kết thúc bình thường** (cannot complete normally). Đây là cách Java phát hiện một đường đi bỏ sót `yield` trước khi chương trình chạy.

## 2. “Kết thúc bình thường” nghĩa là gì?

Theo Java Language Specification (JLS):

- **Normal completion (kết thúc bình thường):** một lệnh/khối thực hiện hết các bước và kết thúc mà không chuyển điều khiển. Chẳng hạn `{ System.out.println("done"); }` có thể chạy đến dấu `}` và kết thúc bình thường.
- **Abrupt completion (kết thúc đột ngột):** điều khiển bị chuyển bởi `throw`, `yield`, `return` hoặc lệnh điều khiển luồng khác tùy vị trí.
- **`yield` có điểm đặc biệt:** bản thân câu lệnh `yield value;` kết thúc đột ngột vì chuyển điều khiển ra khỏi nhánh. Nhưng `switch` expression bao quanh nó **kết thúc bình thường với chính giá trị đó**. Hai cách diễn đạt này không mâu thuẫn.

Các dạng nhánh được dùng trong một `switch` expression:

| Cú pháp nhánh | Cơ chế tạo kết quả | Cần `yield`? |
| --- | --- | --- |
| `case 1 -> "một";` | Biểu thức `"một"` là giá trị trả về | Không |
| `case 2 -> { yield "hai"; }` | `yield` chuyển giá trị ra ngoài khối | Có |
| `default -> throw new IllegalArgumentException();` | Ném ngoại lệ; không có kết quả ở lần đánh giá đó | Không |

Nếu trong khối chỉ có lệnh in, gán biến, ghi log hoặc gọi phương thức `void`, các thao tác đó **không tự trở thành giá trị** của `switch` expression. Đó là lý do Java báo lỗi khi khối có thể chạm dấu `}` mà chưa `yield` hoặc `throw`.

## 3. Quy tắc kiểm tra mọi đường đi của khối nhánh

### 3.1. Sai: chỉ một nhánh của `if` có `yield`

Đây là **đoạn minh họa lỗi biên dịch**, không phải chương trình độc lập:

```java
int n = -4;
String result = switch (n) {
    case 0 -> "không";
    default -> {
        if (n > 0) {
            yield "dương";
        }
        // Khi n âm, khối kết thúc mà không có giá trị.
    }
};
```

Nhánh `default` có một `yield`, nhưng điều đó **chưa đủ**. Khi điều kiện `n > 0` sai, chương trình có thể đi tới hết khối. Trình biên dịch phát hiện đường đi này trước khi chạy.

### 3.2. Đúng: `if/else` bao phủ cả hai lối ra

```java
String result = switch (n) {
    case 0 -> "không";
    default -> {
        if (n > 0) {
            yield "dương";
        } else {
            yield "âm";
        }
    }
};
```

Nếu điều kiện đúng, nhánh đầu tiên `yield`; nếu sai, nhánh thứ hai `yield`. Không còn đường đi nào ra khỏi khối mà thiếu kết quả.

### 3.3. Đúng: chuẩn bị dữ liệu ở các nhánh, `yield` một lần

```java
String result = switch (n) {
    case 0 -> "không";
    default -> {
        String text;
        if (n > 0) {
            text = "dương";
        } else {
            text = "âm";
        }
        yield text;
    }
};
```

Mọi đường đi đều gặp `yield text;`. Java còn kiểm tra riêng rằng `text` đã được gán chắc chắn (definite assignment) khi sử dụng.

### 3.4. Đúng: đường đi không trả kết quả được phép `throw`

```java
String result = switch (n) {
    case 0 -> "không";
    default -> {
        if (n < 0) {
            throw new IllegalArgumentException("n phải >= 0");
        }
        yield "dương";
    }
};
```

Với `n < 0`, chương trình ném ngoại lệ. Với `n > 0`, chương trình sinh kết quả. Không có đường đi nào âm thầm rời khỏi khối.

### 3.5. Sai: chỉ thực hiện tác vụ

```java
String result = switch (n) {
    case 0 -> "không";
    default -> {
        System.out.println("Đã xử lý n");
        // Không có yield hay throw.
    }
};
```

`println` chỉ tạo hiệu ứng phụ; `switch` expression vẫn thiếu giá trị. Nếu cần tạo giá trị, thêm `yield "đã xử lý";`; nếu chỉ cần thực hiện thao tác, dùng `switch` statement phù hợp hơn.

**Cách đọc mã:** với mỗi khối nhánh, thử lần theo mọi lựa chọn `if/else`. Đường nào có thể đến `}` cuối cùng mà không bị `yield`/`throw` chặn lại thì có lỗi.

## 4. Ví dụ Java chạy được: nhánh trực tiếp, `yield` và `throw`

Lưu toàn bộ chương trình sau dưới tên **`SwitchYieldPaths.java`**:

```java
public class SwitchYieldPaths {

    static String classify(int score) {
        return switch (score) {
            case 0 -> "không";

            case 1, 2 -> {
                if (score == 1) {
                    yield "một";
                }
                yield "hai";
            }

            default -> {
                if (score < 0) {
                    throw new IllegalArgumentException(
                        "giá trị âm: " + score
                    );
                }
                yield "lớn hơn hai";
            }
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(0));
        System.out.println(classify(1));
        System.out.println(classify(2));
        System.out.println(classify(7));

        try {
            System.out.println(classify(-2));
        } catch (IllegalArgumentException exception) {
            System.out.println("Lỗi: " + exception.getMessage());
        }
    }
}
```

Biên dịch bằng JDK 17+ có hỗ trợ `--release 14` rồi chạy:

```bash
javac --release 14 SwitchYieldPaths.java
java SwitchYieldPaths
```

Kết quả:

```text
không
một
hai
lớn hơn hai
Lỗi: giá trị âm: -2
```

Phân tích từng đường đi:

1. `score = 0`: `case 0 -> "không"` trả kết quả của biểu thức trực tiếp.
2. `score = 1`: đi vào `case 1, 2`, điều kiện đúng nên `yield "một"`.
3. `score = 2`: điều kiện sai, đi tiếp tới `yield "hai"`.
4. `score = 7`: vào `default`, điều kiện ném lỗi sai, đi tới `yield "lớn hơn hai"`.
5. `score = -2`: vào `default`, `throw` được thực hiện, phương thức `classify` không trả về chuỗi; khối `catch` bên ngoài in thông báo lỗi.

Mỗi đường đi đều có điểm kết thúc rõ ràng: nhận giá trị hoặc ném ngoại lệ. Cấu trúc này tương thích Java 14, không cần tính năng preview hay thư viện bổ sung.

## 5. Đường đi hợp lệ khác với khả năng bao phủ mọi giá trị

Hai quy tắc độc lập phải được thỏa mãn:

**Quy tắc A — Exhaustiveness (bao phủ giá trị):** mỗi giá trị có thể có của selector phải tương ứng với ít nhất một nhãn `case`/`default`. Với `int` hoặc `String` trong Java 14, `switch` expression cần `default`. Với `enum`, nếu liệt kê đủ tất cả hằng enum thì không bắt buộc có `default`. Các bản Java hiện đại mở rộng nhãn và kiểu selector, nhưng vẫn bắt buộc `switch` expression phải bao phủ đầy đủ.

**Quy tắc B — Không rời khối nhánh khi thiếu kết quả:** khi đã chọn nhánh, khối nhánh không được có đường đi kết thúc bình thường mà không `yield` hoặc `throw`.

Ví dụ sau **đã có `default` nên bao phủ `int`**, nhưng vẫn lỗi vì một đường đi của `default` thiếu kết quả:

```java
int number = 5;
String description = switch (number) {
    case 0 -> "không";
    default -> {
        if (number > 10) {
            yield "lớn";
        }
        // number <= 10: có thể hết khối.
    }
};
```

Ngược lại, viết đủ `yield` trong các nhánh có sẵn cũng không sửa được lỗi khi thiếu nhãn để bao phủ một kiểu selector.

Có thêm một quy tắc đặc tả cần biết: một `switch` expression phải có **ít nhất một biểu thức kết quả** (result expression). Nếu tất cả nhánh chỉ `throw` và không có nhánh biểu thức hoặc `yield` nào thì biểu thức đó không đáp ứng yêu cầu này của Java 14. Nếu chỉ cần ném lỗi, hãy sắp xếp lại mã điều khiển luồng để không buộc nó phải là biểu thức tạo giá trị.

## 6. Phân biệt `yield`, `return`, `break`, `throw`

| Câu lệnh | Ý nghĩa | Có phải cách trả giá trị cho `switch` expression? |
| --- | --- | --- |
| `yield value;` | Kết thúc nhánh và chuyển `value` cho `switch` expression gần nhất bao quanh | **Có** |
| `return value;` | Trả về từ phương thức bao ngoài | **Không**, không dùng để nhảy qua `switch` expression |
| `break;` | Kết thúc vòng lặp hoặc `switch` statement theo ngữ cảnh | **Không**, không thay được `yield` |
| `throw exception;` | Ném ngoại lệ, kết thúc đột ngột | Hợp lệ nhưng không sinh giá trị |
| `System.out.println(...);` | Thực hiện tác vụ, sau đó tiếp tục | Không |

Không dùng `return` thay cho `yield` bên trong khối `case -> { ... }` của `switch` expression. Java không cho một lệnh chuyển điều khiển nhảy xuyên qua biểu thức `switch` như vậy. Tương tự, không dùng `break` để “kết thúc nhánh và trả giá trị”.

`yield` bắt buộc có biểu thức mang **giá trị**: `yield;` là sai và `yield aVoidMethod();` cũng sai vì biểu thức có kiểu `void`. Nếu viết `String value = switch (...) { ... };`, các biểu thức kết quả phải tương thích với `String`. Kiểm tra kiểu dữ liệu này độc lập với kiểm tra đường đi.

Một `yield` hướng đến `switch` expression bao quanh gần nhất. Nó không được nhảy ra khỏi một lambda, phương thức hoặc constructor lồng vào trong để tác động đến `switch` khác ở bên ngoài.

## 7. Những sai sót thực tế

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Nhánh có `if (condition) yield value;` nhưng không có `else` | Nếu điều kiện sai, khối có thể kết thúc bình thường | Thêm `else`, `yield` ở cuối hoặc `throw` nếu trường hợp đó không hợp lệ |
| Nhánh gọi `println`, gọi hàm `void` rồi hết khối | Tác vụ không sinh giá trị cho `switch` expression | Thêm `yield` hoặc chọn `switch` statement |
| Có `default` nhưng vẫn không biên dịch | Bao phủ selector không đồng nghĩa mọi đường đi tạo kết quả | Kiểm tra riêng từng đường qua khối nhánh |
| Viết `yield result;` rồi đặt lệnh khác ngay sau trong cùng đường đi | Phần sau không thể thực thi | Đưa tác vụ lên trước `yield` |
| Dùng `return` trong khối nhánh để “trả kết quả” | Chuyển điều khiển sai đích | Thay bằng `yield` |
| Trộn kết quả `String` và kết quả không tương thích kiểu đích | Kiểu biểu thức kết quả không nhất quán với ngữ cảnh | Chọn kiểu kết quả phù hợp hoặc chuyển đổi có chủ ý |
| Không xét nhánh ném ngoại lệ | Nhầm rằng mọi trường hợp đều buộc `yield` | `throw` là lối ra hợp lệ, không tạo giá trị |
| Khối có nhiều điều kiện và vòng lặp phức tạp | Khó chứng minh mọi đường đi đã kết thúc đúng | Tách logic thành phương thức hoặc làm rõ các lối ra `yield`/`throw` |

Khi dùng `try/catch` trong một nhánh, vẫn phải xét mọi lối đi có thể thực hiện, bao gồm cả trường hợp ngoại lệ được bắt và khối `catch` tiếp tục bình thường. Không giả định rằng vì một chỗ có `throw` thì cả nhánh chắc chắn không thể đi tới cuối khối.

## 8. Tự kiểm tra có đáp án

**Câu 1.** Đoạn sau có hợp lệ khi `n` là `int` không?

```java
String answer = switch (n) {
    case 0 -> "zero";
    default -> {
        if (n > 0) {
            yield "positive";
        }
        throw new IllegalArgumentException("negative");
    }
};
```

**Đáp án:** Có. `n == 0` trả `"zero"`; `n > 0` trả `"positive"`; `n < 0` ném ngoại lệ. Không còn đường đi thiếu kết quả.

**Câu 2.** Nếu thay nhánh `default` ở trên bằng khối sau thì sao?

```java
default -> {
    if (n > 0) {
        yield "positive";
    }
    System.out.println("negative");
}
```

**Đáp án:** Không hợp lệ. Khi `n < 0`, lệnh in hoàn tất rồi toàn khối kết thúc bình thường mà không trả giá trị. Có thể thay lệnh in bằng `yield "negative";` hoặc `throw` tùy yêu cầu.

**Câu 3.** `case 0 -> "zero";` có cần `yield` không? **Không.** Giá trị của biểu thức bên phải `->` đã là kết quả của nhánh.

**Câu 4.** Có phải tất cả nhánh đều buộc có `yield`? **Không.** Nhánh trả biểu thức trực tiếp và nhánh `throw` đều hợp lệ. Quy tắc chính xác là không có **khối nhánh nào có thể kết thúc bình thường mà chưa sinh kết quả**.

## 9. Ghi nhớ và nguồn tham khảo

- `switch` expression kết thúc bình thường **phải có giá trị**; một trường hợp ném ngoại lệ không cần có giá trị.
- Khối `case ... -> { ... }` không được có đường đi chạy hết khối mà thiếu `yield` hoặc `throw`.
- `yield` chuyển giá trị cho **biểu thức `switch`**, `return` là dành cho **phương thức**.
- **Bao phủ selector** và **mọi đường đi tạo kết quả** là hai điều kiện riêng.
- Đây là quy tắc Java 14 đã chuẩn hóa và vẫn cần thiết khi lập trình Java hiện tại.

Tài liệu chính thức:

- [JLS Java SE 14 `15.28.1 — The Switch Block of a switch Expression](https://docs.oracle.com/javase/specs/jls/se14/html/jls-15.html#jls-15.28.1).
- [JLS Java SE 14 `14.21 — The yield Statement](https://docs.oracle.com/javase/specs/jls/se14/html/jls-14.html#jls-14.21).
- [Oracle Java 21 — Switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/switch-expressions-and-statements.html).