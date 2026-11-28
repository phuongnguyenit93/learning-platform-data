# Tránh đánh giá lặp biểu thức nguồn có tác dụng phụ

Pattern matching cho `instanceof` được hoàn thiện trong Java 16. Khi viết `source() instanceof String text`, Java đánh giá biểu thức `source()` để lấy một giá trị, kiểm tra giá trị đó có phải `String` hay không và, nếu khớp, gán chính giá trị đã kiểm tra cho biến pattern `text`.

Điều này giúp tránh cách viết cũ phải gọi lại cùng một biểu thức sau khi kiểm tra kiểu. Nếu biểu thức nguồn gọi phương thức có tác dụng phụ, đọc dữ liệu từ hàng đợi, truy vấn trạng thái thay đổi hoặc lấy dữ liệu từ hệ thống bên ngoài, gọi lại có thể tạo ra kết quả khác hoặc thực hiện thao tác hai lần. Pattern variable cho phép kiểm tra kiểu và sử dụng đúng giá trị vừa nhận được trong cùng luồng điều khiển.

Trong module Java 16, pattern matching cho `instanceof` là cải tiến ngôn ngữ vẫn hữu ích trong Java hiện đại, bên cạnh `record` và các API Stream. Bài này tập trung vào việc tránh đánh giá lặp biểu thức nguồn có tác dụng phụ, cách giữ lại một giá trị để phân loại qua nhiều nhánh và giới hạn của pattern variable khi biểu thức được đánh giá nhiều lần. Các ví dụ dùng cú pháp đã được chuẩn hóa, không cần preview feature.

## 1. Mỗi lần đánh giá `instanceof` chỉ lấy giá trị nguồn một lần

Trong biểu thức:

```java
if (readNextValue() instanceof String text) {
    System.out.println(text.strip());
}
```

Java gọi `readNextValue()` để lấy giá trị làm toán hạng bên trái của `instanceof`. Kết quả của lần gọi đó được kiểm tra kiểu. Nếu kết quả là `String`, biến `text` tham chiếu đến chính đối tượng chuỗi vừa lấy được.

Phần thân `if` dùng `text`, không cần gọi lại `readNextValue()` để lấy dữ liệu lần thứ hai. Pattern matching gộp kiểm tra kiểu và khai báo biến vào cùng một biểu thức, giúp tránh việc kiểm tra một giá trị rồi lại lấy một giá trị khác.

Nếu `readNextValue()` trả về `null`, phép `instanceof` cho kết quả `false`, thân `if` không chạy và `text` không được khởi tạo.

## 2. Vấn đề khi gọi lại phương thức nguồn

Trước khi có pattern matching, mã thường kiểm tra kiểu rồi gọi lại phương thức để ép kiểu:

```java
static void processNextValue() {
    if (readNextValue() instanceof String) {
        String text = (String) readNextValue();
        process(text);
    }
}
```

Đoạn mã này gọi `readNextValue()` hai lần nếu lần gọi đầu trả về một `String`. Hai lần gọi không được bảo đảm trả về cùng một đối tượng hoặc cùng một giá trị. Nếu phương thức đọc phần tử tiếp theo từ queue, lần thứ hai có thể lấy phần tử khác. Nếu phương thức cập nhật bộ đếm, ghi log, đọc file hoặc gọi dịch vụ bên ngoài, tác dụng phụ cũng xảy ra hai lần.

Pattern matching giải quyết vấn đề bằng cách dùng lại giá trị đã được kiểm tra:

```java
static void processNextValue() {
    if (readNextValue() instanceof String text) {
        process(text);
    }
}
```

Trong phiên bản này, `readNextValue()` chỉ được gọi một lần cho mỗi lần thực hiện câu lệnh `if`. Biến `text` nhận giá trị của chính lần gọi đó.

## 3. Vì sao gọi lại có thể làm sai logic?

Một biểu thức nguồn có tác dụng phụ không nhất thiết trả về cùng kết quả ở mọi lần gọi. Ví dụ, phương thức lấy phần tử tiếp theo của hàng đợi có thể tiêu thụ một phần tử mỗi lần gọi:

```java
Object readNextValue() {
    return queue.poll();
}
```

Giả sử queue chứa hai phần tử: chuỗi `"first"` và số `42`.

```java
if (readNextValue() instanceof String) {
    String text = (String) readNextValue();
    process(text);
}
```

Lần gọi đầu lấy `"first"` và phép kiểm tra kiểu thành công. Lần gọi thứ hai lấy `42`; phép ép kiểu sang `String` gây `ClassCastException`. Mã đã kiểm tra một phần tử nhưng lại xử lý phần tử kế tiếp.

Với pattern variable:

```java
if (readNextValue() instanceof String text) {
    process(text);
}
```

Phần tử được kiểm tra cũng chính là phần tử được xử lý. Không có lần đọc queue thứ hai.

## 4. Giữ lại kết quả khi cần phân loại qua nhiều nhánh

Nếu cần kiểm tra cùng một kết quả qua nhiều nhánh, hãy đánh giá biểu thức nguồn một lần và lưu vào biến cục bộ:

```java
static void processValue() {
    Object candidate = readNextValue();

    if (candidate instanceof String text) {
        processText(text);
    } else if (candidate instanceof Integer number) {
        processNumber(number);
    } else {
        processUnsupported(candidate);
    }
}
```

`readNextValue()` chỉ chạy một lần. Các điều kiện tiếp theo kiểm tra cùng tham chiếu `candidate`, vì vậy mọi nhánh đều phân loại cùng một kết quả. Đây là cách phù hợp khi một giá trị có thể thuộc nhiều kiểu khác nhau và chương trình cần chọn một nhánh xử lý.

Không nên viết như sau nếu mục tiêu là phân loại cùng một kết quả:

```java
if (readNextValue() instanceof String text) {
    processText(text);
} else if (readNextValue() instanceof Integer number) {
    processNumber(number);
}
```

Khi điều kiện đầu sai, điều kiện `else if` gọi `readNextValue()` lần nữa. Hai nhánh có thể đang kiểm tra hai phần tử khác nhau. Dùng biến `candidate` để bảo đảm các nhánh làm việc trên cùng dữ liệu.

## 5. Dùng pattern variable ở các điều kiện tiếp theo thay vì gọi lại accessor

Không chỉ phương thức đọc dữ liệu mới có thể có tác dụng phụ. Một accessor hoặc getter cũng có thể truy vấn trạng thái thay đổi, tính toán tốn kém hoặc trả về đối tượng khác nhau qua mỗi lần gọi.

Ví dụ không nên lặp lại lời gọi `profile()`:

```java
if (user.profile() instanceof Profile profile
        && user.profile().isEnabled()) {
    open(profile);
}
```

Vế trái gọi `user.profile()` để lấy đối tượng và kiểm tra kiểu. Vế phải lại gọi `user.profile()` lần nữa. Nếu getter trả về đối tượng khác hoặc có tác dụng phụ, điều kiện có thể kiểm tra một profile nhưng lại kiểm tra trạng thái của profile khác.

Hãy dùng biến pattern cho giá trị đã lấy:

```java
if (user.profile() instanceof Profile profile
        && profile.isEnabled()) {
    open(profile);
}
```

`user.profile()` chỉ được gọi một lần. Cả `isEnabled()` và `open()` đều sử dụng cùng đối tượng được pattern xác nhận.

## 6. Kết hợp với `&&` và short-circuit

Toán tử `&&` đánh giá từ trái sang phải và chỉ đánh giá vế phải khi vế trái đúng. Vì vậy, có thể lấy dữ liệu, xác nhận kiểu rồi kiểm tra tiếp trên biến pattern:

```java
if (readNextValue() instanceof String command
        && !command.isBlank()
        && command.startsWith("deploy:")) {
    execute(command.strip());
}
```

Trình tự thực hiện:

1. `readNextValue()` được gọi một lần trong lần đánh giá điều kiện này.
2. Nếu giá trị không phải `String` hoặc là `null`, các vế sau bị bỏ qua.
3. Nếu là `String`, biến `command` được gán và có thể dùng trong các vế phải.
4. Nếu chuỗi blank, Java bỏ qua vế `startsWith` và thân `if`.
5. Chỉ khi mọi điều kiện đúng, `execute(command.strip())` được gọi.

Không cần gọi lại `readNextValue()` trong các vế sau. Hãy dùng `command` để mọi phép kiểm tra đều áp dụng trên cùng giá trị.

## 7. Lưu ý với `||` và các biểu thức nguồn lặp lại

Toán tử `||` chỉ đánh giá vế phải khi vế trái sai. Nếu viết cùng một lời gọi nguồn ở cả hai vế, phương thức có thể được gọi hai lần:

```java
boolean supported = readNextValue() instanceof String
        || readNextValue() instanceof Integer;
```

Nếu kết quả đầu tiên là `String`, vế phải không chạy. Nếu kết quả đầu tiên không phải `String`, vế phải gọi `readNextValue()` lần thứ hai và có thể nhận một phần tử khác. Khi cần kiểm tra một giá trị duy nhất, lưu kết quả trước:

```java
Object candidate = readNextValue();
boolean supported = candidate instanceof String
        || candidate instanceof Integer;
```

Hoặc dùng các nhánh riêng nếu cần pattern variable để xử lý từng kiểu:

```java
Object candidate = readNextValue();

if (candidate instanceof String text) {
    processText(text);
} else if (candidate instanceof Integer number) {
    processNumber(number);
}
```

Không cố dùng biến pattern được khai báo ở vế trái của OR trong vế phải hoặc trong thân `if` nếu kết quả điều kiện không chứng minh biến đã khớp. Quy tắc flow scoping vẫn được áp dụng như các biểu thức `instanceof` khác.

## 8. Phân biệt một lần đánh giá với nhiều lần thực thi

Pattern matching bảo đảm biểu thức nguồn được đánh giá một lần trong **mỗi lần thực thi biểu thức `instanceof`**. Điều đó không có nghĩa phương thức nguồn chỉ được gọi một lần trong toàn bộ chương trình.

Ví dụ trong vòng lặp:

```java
while (readNextValue() instanceof String text) {
    process(text);
}
```

Mỗi lần kiểm tra điều kiện `while`, `readNextValue()` được gọi một lần. Vòng lặp có thể gọi phương thức nhiều lần vì điều kiện được đánh giá lại sau mỗi vòng. Đây thường là hành vi mong muốn khi phương thức lấy phần tử tiếp theo từ queue.

Nếu cần đọc đúng một lần rồi xử lý giá trị đó trong nhiều câu lệnh, hãy đưa lời gọi ra ngoài điều kiện:

```java
Object candidate = readNextValue();

if (candidate instanceof String text) {
    process(text);
    audit(text);
}
```

Ở đây, `readNextValue()` chỉ được gọi một lần trong phương thức. Hai thao tác `process` và `audit` cùng nhận chuỗi đã được kiểm tra.

## 9. Pattern variable giữ tham chiếu, không tạo bản sao dữ liệu

Biến pattern nhận giá trị tham chiếu được trả về bởi biểu thức nguồn. Nó không tự động sao chép sâu đối tượng:

```java
if (loadBuffer() instanceof StringBuilder buffer) {
    buffer.append(" processed");
}
```

`buffer` tham chiếu đến đối tượng `StringBuilder` mà `loadBuffer()` trả về. Việc gọi `append()` thay đổi chính đối tượng đó. Pattern matching giúp không phải gọi lại `loadBuffer()` để lấy đối tượng sau khi kiểm tra kiểu, nhưng không tạo snapshot bất biến của trạng thái đối tượng.

Nếu cần một bản sao độc lập, phải tạo bản sao bằng API phù hợp với kiểu dữ liệu:

```java
if (loadBuffer() instanceof StringBuilder buffer) {
    StringBuilder copy = new StringBuilder(buffer);
    copy.append(" processed");
    save(copy);
}
```

Lời gọi `loadBuffer()` vẫn chỉ được thực hiện một lần trong biểu thức `instanceof`; `copy` là một đối tượng mới được tạo có chủ đích.

## 10. Những trường hợp cần lưu kết quả vào biến cục bộ

| Nhu cầu | Cách viết phù hợp | Lý do |
|---|---|---|
| Kiểm tra một giá trị và xử lý ngay | `source() instanceof String text` | Nguồn được đánh giá một lần và giá trị khớp được bind vào `text`. |
| Phân loại cùng một kết quả qua nhiều nhánh | `Object value = source();` rồi kiểm tra `value` | Các nhánh cùng kiểm tra một giá trị. |
| Dùng kết quả ở nhiều câu lệnh | Lưu kết quả vào biến cục bộ | Tránh gọi lại phương thức nguồn. |
| Dùng accessor trong nhiều điều kiện | Bind kết quả accessor vào pattern variable hoặc biến cục bộ | Không gọi getter nhiều lần và tránh đọc các trạng thái khác nhau. |
| Cố ý lấy phần tử tiếp theo qua từng vòng | Gọi nguồn trong điều kiện vòng lặp | Mỗi lần lặp là một lần đọc mới có chủ đích. |
| Cần bản sao độc lập | Tạo bản sao sau khi pattern khớp | Pattern variable chỉ giữ tham chiếu, không clone đối tượng. |

## 11. Ví dụ hoàn chỉnh

```java
import java.util.ArrayDeque;
import java.util.Queue;

public class PatternSingleEvaluationDemo {
    private static final Queue<Object> VALUES = new ArrayDeque<>();

    static Object readNextValue() {
        return VALUES.poll();
    }

    static void processText(String text) {
        System.out.println("Text: " + text.strip());
    }

    static void processNumber(Integer number) {
        System.out.println("Number: " + number);
    }

    static void processNextValue() {
        Object candidate = readNextValue();

        if (candidate instanceof String text) {
            processText(text);
        } else if (candidate instanceof Integer number) {
            processNumber(number);
        } else {
            System.out.println("Unsupported value: " + candidate);
        }
    }

    public static void main(String[] args) {
        VALUES.add("first");
        VALUES.add(42);

        processNextValue();
        processNextValue();
    }
}
```

Trong `processNextValue()`, queue chỉ được đọc một lần cho mỗi lần gọi phương thức. Biến `candidate` giữ kết quả để các nhánh `if` và `else if` phân loại cùng một phần tử. Nếu gọi `readNextValue()` trực tiếp trong từng điều kiện, nhánh sau có thể đọc phần tử kế tiếp thay vì phần tử đã kiểm tra ở nhánh trước.

Có thể biên dịch bằng JDK 16 trở lên. Khi dùng JDK mới và muốn kiểm tra cú pháp theo mức ngôn ngữ Java 16:

```bash
javac --release 16 PatternSingleEvaluationDemo.java
java PatternSingleEvaluationDemo
```

## 12. Cách áp dụng trong mã Java hiện đại

- Dùng pattern variable để kiểm tra kiểu và giữ lại ngay giá trị vừa được biểu thức nguồn trả về.
- Không gọi lại phương thức có tác dụng phụ chỉ để ép kiểu giá trị đã kiểm tra.
- Nếu cần nhiều nhánh xử lý cùng một kết quả, đánh giá nguồn một lần vào biến cục bộ rồi kiểm tra biến đó.
- Dùng biến pattern trong các vế phải của `&&` để kiểm tra tiếp trên đúng đối tượng đã khớp.
- Kiểm tra các biểu thức `||`, biểu thức ba ngôi và điều kiện lồng để phát hiện lời gọi nguồn bị lặp ở nhiều vị trí.
- Nhớ rằng mỗi lần đánh giá lại điều kiện vòng lặp sẽ gọi lại biểu thức nguồn; đây có thể là hành vi mong muốn hoặc cần chuyển ra ngoài vòng lặp.
- Pattern variable giữ tham chiếu đến đối tượng, không tạo bản sao sâu hay bảo đảm đối tượng không thay đổi.

Pattern matching cho `instanceof` giúp gắn kết quả của một lần đánh giá với biến có kiểu đã kiểm tra. Khi biểu thức nguồn có tác dụng phụ hoặc có thể trả về kết quả khác nhau, dùng pattern variable hoặc lưu kết quả vào biến cục bộ sẽ tránh kiểm tra một giá trị rồi xử lý một giá trị khác. Quy tắc này tiếp tục hữu ích trong Java hiện đại.
