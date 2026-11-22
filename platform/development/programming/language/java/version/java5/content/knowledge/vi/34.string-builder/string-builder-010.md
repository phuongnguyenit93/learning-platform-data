# Chuyển kết quả StringBuilder sang String

## 1. Vì sao cần một bước kết thúc?

`StringBuilder` phù hợp trong giai đoạn ghép và chỉnh sửa văn bản. Nhưng kết quả mà một hàm trả về, một đối tượng nghiệp vụ lưu lại hoặc một API nhận vào thường cần là `String`: một giá trị văn bản bất biến.

Có thể hình dung quá trình làm việc thành hai giai đoạn:

```text
Tạo builder → thêm/sửa nội dung → gọi toString() → nhận String kết quả
```

Gọi `toString()` không biến đối tượng builder thành một đối tượng kiểu khác. Nó trả về một `String` biểu diễn nội dung hiện có; builder vẫn tồn tại và vẫn sửa được.

Cú pháp thường dùng, minh họa bên trong một phương thức:

```java
StringBuilder builder = new StringBuilder();
builder.append("Hello, ").append("Lan").append('!');
String message = builder.toString();
```

Sau đoạn mã, `message` có nội dung `"Hello, Lan!"`. Biến `builder` vẫn có kiểu `StringBuilder`.

Các ví dụ trong bài dùng Java 17 trở lên và các API vẫn được sử dụng trong Java hiện nay.

## 2. Hợp đồng của toString()

Chữ ký:

```java
public String toString()
```

Phương thức không nhận tham số. Kết quả chứa nội dung builder tại thời điểm chuyển đổi. Các thay đổi tiếp theo của builder không làm thay đổi `String` đã nhận. Đây là cam kết được nêu trong [Java API: StringBuilder.toString()](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StringBuilder.html#toString()).

Cần tách ba điều thường bị nhầm:

- `toString()` không xóa hoặc làm rỗng builder.
- `toString()` không khóa builder để cấm sửa tiếp.
- `String` kết quả không phải cửa sổ tự cập nhật theo builder.

Tính bất biến thuộc về đối tượng `String`. Ta vẫn có thể gán một giá trị khác cho biến đang giữ chuỗi:

```java
String text = builder.toString();
text = text + " Goodbye!";
```

Dòng thứ hai thay giá trị tham chiếu mà biến `text` giữ; nó không sửa nội dung của `String` cũ và cũng không sửa builder. `final`, nếu được dùng cho biến, chỉ cấm gán lại biến; không phải thứ tạo ra tính bất biến của `String`.

### 2.1. Một ví dụ đầy đủ về kết quả độc lập

Lưu chương trình sau thành `BuilderResultDemo.java`:

```java
public class BuilderResultDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("status=");
        builder.append("NEW");

        String first = builder.toString();
        CharSequence alias = builder;

        builder.setLength(0);
        builder.append("status=DONE");
        String second = builder.toString();

        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("builder=" + builder);
        System.out.println("alias=" + alias);
        System.out.println("firstIsString=" + (first instanceof String));
        System.out.println("sameText=" + first.equals(second));
        System.out.println("empty=["
                + new StringBuilder().toString() + "]");
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 --release 17 BuilderResultDemo.java
java BuilderResultDemo
```

Stdout:

```text
first=status=NEW
second=status=DONE
builder=status=DONE
alias=status=DONE
firstIsString=true
sameText=false
empty=[]
```

`first` giữ kết quả của lần chuyển đổi đầu, kể cả sau khi builder bị làm rỗng rồi ghi nội dung khác. `second` là kết quả của trạng thái mới.

Ngược lại, `alias` chỉ là một biến khác trỏ tới chính builder. Gán builder cho một biến kiểu `CharSequence` không tạo chuỗi độc lập. Khi in `alias`, ta thấy nội dung hiện tại của builder.

Builder rỗng chuyển thành chuỗi rỗng `""`, không phải `null`. Hai dấu ngoặc trong dòng `empty=[]` do chương trình tự ghép thêm để giúp nhìn thấy trường hợp rỗng.

## 3. Đặt toString() tại ranh giới trả kết quả

Khi một hàm có trách nhiệm tạo một văn bản hoàn chỉnh, một mẫu dễ hiểu là giữ builder trong hàm và chỉ trả về `String` khi đã ghép xong.

Chương trình sau tạo một dòng liệt kê nhãn. Lưu thành `TagLineDemo.java`:

```java
import java.util.List;
import java.util.Objects;

public class TagLineDemo {
    private static String makeTagLine(List<String> tags) {
        Objects.requireNonNull(tags, "tags");

        StringBuilder builder = new StringBuilder("Tags: ");
        for (int i = 0; i < tags.size(); i++) {
            String tag = Objects.requireNonNull(tags.get(i), "tag");
            if (i > 0) {
                builder.append(", ");
            }
            builder.append(tag);
        }
        return builder.toString();
    }

    private static void deliver(String text) {
        System.out.println("delivered=" + text);
    }

    public static void main(String[] args) {
        String line = makeTagLine(List.of("java", "jvm", "gradle"));
        deliver(line);
        System.out.println("emptyList=[" + makeTagLine(List.of()) + "]");
        System.out.println("length=" + line.length());
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 --release 17 TagLineDemo.java
java TagLineDemo
```

Stdout:

```text
delivered=Tags: java, jvm, gradle
emptyList=[Tags: ]
length=23
```

Dấu cách ngay trước dấu `]` ở dòng thứ hai là dữ liệu thật: hàm luôn tạo tiền tố `"Tags: "`, kể cả khi danh sách rỗng. `toString()` giữ nguyên nội dung, không tự `trim`.

Trong thiết kế này:

1. Hàm tự quản lý builder của nó.
2. Mỗi vòng lặp chỉ bổ sung dữ liệu.
3. Hàm gọi `toString()` một lần sau khi ghép xong.
4. Bên gọi nhận một giá trị văn bản và không thể sửa builder nội bộ thông qua kết quả đó.

Hàm `deliver` khai báo nhận `String`, nên bên gọi phải cung cấp một `String`. Java không tự gọi `toString()` cho mọi đối tượng chỉ vì tham số hàm cần chuỗi.

Ví dụ sau chỉ minh họa lỗi biên dịch, không phải một chương trình cần chạy:

```java
StringBuilder builder = new StringBuilder("ready");
// deliver(builder); // Sai kiểu: StringBuilder không phải String.
deliver(builder.toString());
```

Nếu thiết kế một hàm khác chỉ cần đọc đồng bộ trong lúc gọi và chấp nhận nhiều loại chuỗi ký tự, tham số `CharSequence` có thể phù hợp. Nhưng quyết định nhận `CharSequence` không đồng nghĩa với việc đã có một giá trị bất biến để giữ lại lâu dài.

## 4. Gọi phương thức khác với ép kiểu

Hai lớp `String` và `StringBuilder` khác nhau. Không thể dùng phép ép kiểu để yêu cầu JVM chuyển nội dung builder thành chuỗi.

Các dòng sai dưới đây được đặt trong chú thích:

```java
StringBuilder builder = new StringBuilder("abc");

// String a = builder;          // Không có phép gán ngầm.
// String b = (String) builder; // Hai lớp không tương thích.

Object value = builder;
// String c = (String) value;   // Biên dịch được nhưng chạy sẽ lỗi
                               // ClassCastException.

String result = builder.toString(); // Chuyển nội dung đúng cách.
```

Khi `value` có kiểu khai báo là `Object`, trình biên dịch cho phép thử ép sang `String`; lúc chạy, đối tượng thật vẫn là builder nên phép ép thất bại. Phép ép kiểu kiểm tra hoặc thay cách nhìn về kiểu, không phải lời gọi một phép chuyển đổi dữ liệu.

Cũng có constructor hiện hành `new String(builder)`. Nó tạo chuỗi từ nội dung builder, nhưng trong mã thông thường `builder.toString()` đã diễn đạt trực tiếp ý định lấy kết quả. Không cần bọc thêm `new String(builder.toString())` chỉ để bảo đảm kết quả không thay đổi theo builder.

## 5. toString(), String.valueOf và null

Khi đã có một builder hợp lệ, `builder.toString()` là cách rõ ràng.

Nếu biến builder có thể là `null`, gọi phương thức qua biến đó ném `NullPointerException`. Trong khi đó, `String.valueOf(Object)` trả chuỗi `"null"` khi đối số là `null`; với đối số khác `null`, nó dùng `toString()`. Quy tắc này được mô tả tại [Java API: String.valueOf(Object)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#valueOf(java.lang.Object)).

Chương trình độc lập sau dùng biến có kiểu `StringBuilder`, vì vậy lời gọi `String.valueOf(missing)` chọn overload nhận `Object`. Lưu thành `BuilderNullDemo.java`:

```java
public class BuilderNullDemo {
    public static void main(String[] args) {
        StringBuilder missing = null;
        StringBuilder empty = new StringBuilder();
        StringBuilder present = new StringBuilder("ready");

        System.out.println("missing=[" + String.valueOf(missing) + "]");
        System.out.println("empty=[" + empty.toString() + "]");
        System.out.println("present=[" + present.toString() + "]");

        try {
            missing.toString();
        } catch (NullPointerException ex) {
            System.out.println("directCall=NullPointerException");
        }

        String fallback = missing == null ? "" : missing.toString();
        System.out.println("fallback=[" + fallback + "]");
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 --release 17 BuilderNullDemo.java
java BuilderNullDemo
```

Stdout:

```text
missing=[null]
empty=[]
present=[ready]
directCall=NullPointerException
fallback=[]
```

Ba trạng thái cần phân biệt:

| Trạng thái | Ý nghĩa | Hành vi trong ví dụ |
| --- | --- | --- |
| Builder là `null` | Không có đối tượng builder | Gọi trực tiếp gây lỗi |
| Builder tồn tại nhưng rỗng | Có đối tượng, chưa có nội dung | `toString()` trả `""` |
| Builder chứa văn bản `"null"` | Có bốn chữ cái thực sự | `toString()` trả `"null"` |

Không dùng `String.valueOf` chỉ để che giấu dữ liệu thiếu nếu ứng dụng yêu cầu dữ liệu bắt buộc. Chọn rõ hợp đồng: báo lỗi, dùng giá trị mặc định, hoặc chấp nhận văn bản `"null"`.

Cũng không suy từ ví dụ trên rằng lời gọi `String.valueOf(null)` viết trực tiếp với literal `null` có cùng hành vi: `String` còn overload nhận `char[]`, và việc chọn overload có thể dẫn tới `NullPointerException`. Muốn nhấn mạnh trường hợp overload nhận đối tượng, dùng `String.valueOf((Object) null)`; trong mã ứng dụng, ưu tiên xử lý dữ liệu thiếu theo ý nghĩa nghiệp vụ.

## 6. So sánh nội dung sau chuyển đổi

Sau khi có `String`, dùng `equals` để so sánh nội dung. Không dùng `==` để suy ra hai kết quả có cùng văn bản.

Đoạn minh họa trong một phương thức:

```java
StringBuilder builder = new StringBuilder("abc");
String first = builder.toString();
String second = builder.toString();

boolean sameContent = first.equals(second); // true
boolean matchesLiteral = "abc".equals(first); // true
```

Không đưa `first == second` vào logic nghiệp vụ. Nó hỏi hai biến có trỏ cùng đối tượng hay không, trong khi yêu cầu ở đây là so sánh giá trị văn bản. Việc dùng lại đối tượng hoặc tối ưu bộ nhớ là chi tiết không cần dựa vào.

Nếu chỉ cần so một `String` với nội dung builder và không cần giữ kết quả độc lập, có thể dùng `"abc".contentEquals(builder)`. Ngược lại, `"abc".equals(builder)` cho `false`, vì đối tượng đối chiếu không phải `String`. Đây là lý do phải phân biệt “cùng nội dung” với “cùng loại đối tượng”.

## 7. Chi phí chuyển đổi và thời điểm nên chuyển

Một chuỗi kết quả cần biểu diễn toàn bộ văn bản đã xây dựng. Trong các JDK thường dùng, tạo kết quả từ builder có chi phí theo lượng nội dung phải chuyển; không nên giả định việc đó luôn miễn phí hoặc chỉ là đổi kiểu tham chiếu.

Với yêu cầu chỉ lấy kết quả cuối, tránh mẫu gọi `toString()` ở mọi vòng lặp. Ví dụ đối chiếu sau chỉ minh họa trong một phương thức:

```java
StringBuilder builder = new StringBuilder();
for (int i = 0; i < 1000; i++) {
    builder.append('x');
}
String result = builder.toString();
```

Nếu trong mỗi vòng lại lấy một chuỗi mới chứa toàn bộ tiền tố, lượng văn bản xử lý cộng dồn có thể tăng theo `1 + 2 + ... + n`. Đó là công việc thừa khi chương trình chỉ cần kết quả cuối.

Tuy nhiên, nếu nghiệp vụ cần lưu từng phiên bản, gọi `toString()` ở các mốc đó là có chủ đích. Điều cần tránh là tạo kết quả trung gian rồi bỏ đi, hoặc lặp lại cùng một lần chuyển đổi khi một biến `String` đã đủ cho nhiều lần sử dụng.

Không cần gọi `trimToSize()` trước `toString()` chỉ để lấy kết quả. Dung lượng dự trữ của builder không trở thành phần nội dung dư ở cuối chuỗi kết quả.

## 8. Những việc toString() không tự xử lý

- **Không chuẩn hóa văn bản:** dấu cách, xuống dòng và dữ liệu hiện có vẫn được giữ. Nếu cần chuẩn hóa, phải quy định và thực hiện riêng.
- **Không mã hóa thành byte:** `String` là văn bản. Chỉ khi xuất sang tệp, mạng hoặc byte array mới cần lựa chọn bộ mã ký tự phù hợp, chẳng hạn UTF-8.
- **Không tự escape dữ liệu:** kết quả không tự trở thành JSON, HTML hay truy vấn SQL hợp lệ. Dùng API xử lý đúng định dạng ở bước tương ứng.
- **Không tạo an toàn luồng cho builder:** kết quả `String` bất biến không làm cho việc đọc builder trong lúc một luồng khác đang sửa trở nên an toàn.

Cách dễ quản lý nhất trong ví dụ tạo văn bản là dùng builder cục bộ rồi trả kết quả. Nếu phải chia sẻ một builder, cần cơ chế đồng bộ bao phủ cả phần sửa và phần chuyển đổi; không nên coi `toString()` là một thao tác tự bảo đảm lấy trạng thái nhất quán khi có ghi đồng thời.

## 9. Tự kiểm tra

Cho đoạn mã:

```java
StringBuilder builder = new StringBuilder("A");
String saved = builder.toString();
builder.append('B');
String latest = builder.toString();
```

Hãy trả lời:

1. `saved`, `latest` và builder có nội dung gì?
2. Gọi `toString()` lần đầu có làm builder rỗng không?
3. Nếu thay `String saved = builder.toString();` bằng `CharSequence saved = builder;`, khi đọc `saved` sau lệnh `append` sẽ thấy gì?
4. Nếu hàm khai báo trả về `String`, có thể viết `return builder;` không?
5. Một builder rỗng chuyển thành `null` hay `""`?
6. Vì sao không dùng `==` để kiểm tra hai lần chuyển đổi có cùng văn bản?
7. Có nên chuyển sang chuỗi ở mỗi vòng lặp nếu chỉ cần kết quả cuối?

Đáp án:

1. `saved` là `"A"`, `latest` và builder có nội dung `"AB"`.
2. Không. Builder vẫn giữ nội dung và sửa được.
3. Thấy `"AB"`, vì biến đó trỏ tới builder.
4. Không. Cần `return builder.toString();`.
5. Chuỗi rỗng `""`.
6. `==` kiểm tra danh tính đối tượng; `equals` kiểm tra nội dung chuỗi.
7. Không cần; ghép xong rồi chuyển một lần giúp tránh tạo kết quả trung gian thừa.

Hãy coi `toString()` là ranh giới lấy một giá trị văn bản hoàn chỉnh: xây dựng bằng builder, chuyển khi cần kết quả, rồi sử dụng `String` theo hợp đồng của bên nhận.
