# append cho chuỗi, kiểu nguyên thủy và đối tượng

## 1. append làm gì và vì sao cần nhiều phiên bản?

Khi tạo thông báo hoặc báo cáo, các phần dữ liệu thường không cùng kiểu: tên là String, số lượng là int, trạng thái là boolean, còn một mặt hàng là đối tượng tự định nghĩa.

**StringBuilder.append(...)** thêm biểu diễn ký tự của dữ liệu vào **cuối nội dung hiện có**. Phương thức sửa chính builder và trả lại builder đó, nên có thể nối nhiều lời gọi:

```java
StringBuilder result = new StringBuilder();
result.append("count=").append(3).append(", ready=").append(true);
// Noi dung: "count=3, ready=true"
```

Đây là đoạn minh họa bên trong một phương thức. Không cần gọi String.valueOf trước mọi append; các phiên bản nhận kiểu nguyên thủy đã đảm nhiệm việc thêm biểu diễn văn bản phù hợp.

Các phiên bản cùng tên nhưng khác kiểu tham số gọi là **nạp chồng (overload)**. Phân biệt chúng giúp giải thích vì sao append(65) thêm hai chữ số, append('A') thêm một ký tự, còn append((char[]) null) gây lỗi.

Hợp đồng từng phiên bản được mô tả trong [Java SE 21 StringBuilder API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StringBuilder.html).

## 2. Thêm String và CharSequence

### 2.1. String: thêm nội dung của chuỗi

```java
StringBuilder message = new StringBuilder("Hello");
message.append(", ").append("An").append('!');
// "Hello, An!"
```

append không thay đổi các String truyền vào. Nó đọc nội dung và bổ sung vào builder. Nếu builder đã chứa dữ liệu thì dữ liệu mới được nối sau, không thay toàn bộ nội dung cũ.

Gọi append("") không thêm ký tự. Gọi append(" ") thêm một dấu cách thật. Khoảng trắng và xuống dòng đều là dữ liệu; muốn có chúng phải thêm có chủ đích.

### 2.2. CharSequence: thêm dãy ký tự hiện tại

StringBuilder và String đều có thể được sử dụng như CharSequence. Khi thêm nội dung từ một builder khác, builder đích nhận dãy ký tự tại lúc gọi; nó không lưu một liên kết theo dõi để cập nhật theo nguồn về sau:

```java
StringBuilder source = new StringBuilder("draft");
StringBuilder target = new StringBuilder().append(source);
source.append("!");

// source: "draft!"
// target: "draft"
```

Điều này khác với phép gán target = source, vốn làm hai biến cùng tham chiếu một đối tượng.

Nếu một đối tượng tự triển khai CharSequence, phiên bản append(CharSequence) làm việc theo hợp đồng dãy ký tự. Không mặc định rằng mọi đối tượng truyền vào đều được xử lý bằng toString; phải xem phiên bản nạp chồng được chọn.

### 2.3. Chỉ thêm một đoạn

Đối với CharSequence, tham số cuối là **vị trí kết thúc không được lấy**:

```java
StringBuilder part = new StringBuilder();
part.append("ABCDE", 1, 3);
// Lay chi so 1 va 2 -> "BC".
```

Các chỉ số dựa trên đơn vị char UTF-16. Khi văn bản có ký tự bổ sung được biểu diễn bằng cặp surrogate, một phạm vi tùy ý có thể cắt đôi ký tự; append theo phạm vi không tự điều chỉnh theo ký tự hiển thị.

## 3. Thêm kiểu nguyên thủy: giá trị nào thành văn bản nào?

| Đối số | Phiên bản tiêu biểu | Nội dung được thêm |
| --- | --- | --- |
| true | append(boolean) | true |
| 'X' | append(char) | X |
| 42 | append(int) | 42 |
| 9000000000L | append(long) | 9000000000 |
| 1.5f | append(float) | 1.5 |
| 2.25d | append(double) | 2.25 |

Không có phiên bản riêng append(byte) hoặc append(short). Với biến byte/short trong lời gọi trực tiếp, Java có thể mở rộng giá trị sang int rồi dùng append(int). Không cần ép kiểu sang String.

### 3.1. Số không tự trở thành mã ký tự

```java
StringBuilder a = new StringBuilder().append(65);
StringBuilder b = new StringBuilder().append('A');
// a chua "65"; b chua "A".
```

append(int) thêm biểu diễn thập phân của số nguyên. Nếu thật sự có một điểm mã Unicode và muốn thêm ký tự tương ứng, API dành cho nhu cầu đó là appendCodePoint(int), không phải append(int).

### 3.2. Biểu thức được tính trước khi append nhận giá trị

```java
StringBuilder a = new StringBuilder().append(1).append(2);
StringBuilder b = new StringBuilder().append(1 + 2);
StringBuilder c = new StringBuilder().append('A' + 1);
// a: "12"
// b: "3"
// c: "66"
```

Trong lời gọi cuối, phép cộng số học làm 'A' được chuyển sang giá trị số rồi cộng 1, tạo int bằng 66. append nhận 66 nên thêm "66", không tự suy ra người viết muốn ký tự tiếp theo.

Muốn in phép tính có kết quả, tách rõ nhãn và giá trị:

```java
int x = 1;
int y = 2;
StringBuilder result = new StringBuilder();
result.append("sum=").append(x + y);
// "sum=3"
```

### 3.3. append không phải công cụ định dạng số theo yêu cầu trình bày

Thêm double bằng append không có nghĩa làm tròn hai chữ số thập phân, chèn dấu phân nhóm hay dùng dấu phẩy thập phân theo Locale. Các biểu diễn mặc định của kiểu số được dùng.

Nếu yêu cầu là giá tiền, tỷ lệ hoặc báo cáo theo vùng, hãy định dạng bằng công cụ phù hợp rồi append chuỗi kết quả. Không sửa kết quả bằng cách thêm ngẫu nhiên ".00" vì cách đó không xử lý đúng mọi giá trị.

## 4. Thêm đối tượng: vai trò của toString

Với **append(Object)**, việc chuyển đối tượng thành chuỗi được xác định theo String.valueOf(Object): nếu đối tượng null thì dùng "null"; nếu không null thì dùng toString của đối tượng. Quy tắc này được mô tả trong [Java SE 21 String.valueOf(Object)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#valueOf(java.lang.Object)).

Ví dụ một lớp Product có toString được định nghĩa rõ ràng sẽ tạo nội dung như:

```text
Product{code=P01, stock=8}
```

Nếu không ghi đè toString, biểu diễn mặc định thường chỉ có thông tin nhận diện đối tượng, không phải danh sách các trường có ý nghĩa nghiệp vụ. append không tự phản chiếu tất cả thuộc tính của lớp.

Cần phân biệt hai lựa chọn:

- Muốn thông tin mô tả đối tượng để chẩn đoán: toString có thể phù hợp.
- Muốn một định dạng dữ liệu ổn định để trao đổi hoặc lưu trữ: chọn cách chuyển đổi có hợp đồng rõ ràng, không mặc định toString là định dạng tuần tự hóa.

Phương thức toString cũng là mã do lớp đối tượng thực thi. Nó có thể tốn thời gian hoặc phát ngoại lệ; append(Object) không bảo đảm mọi đối tượng đều được chuyển thành văn bản thành công. Những phần đã append trước đó không tự hoàn tác nếu một bước sau thất bại.

## 5. Nạp chồng được chọn theo kiểu ở thời điểm biên dịch

Đối tượng thực tế và kiểu của biểu thức truyền vào đều quan trọng.

Với một char[]:

```java
char[] letters = {'A', 'B', 'C'};
Object reference = letters;

StringBuilder a = new StringBuilder().append(letters);
StringBuilder b = new StringBuilder().append(reference);
// a them noi dung ABC.
// b dung append(Object), khong them tung phan tu nhu append(char[]).
```

Ở lời gọi đầu, đối số có kiểu char[] nên phiên bản dành cho mảng ký tự được chọn. Ở lời gọi sau, biểu thức reference có kiểu Object nên append(Object) được chọn, dù đối tượng đang được tham chiếu vẫn là mảng char.

Việc chọn chữ ký phương thức nạp chồng được thực hiện khi biên dịch; điều này khác với việc gọi đúng triển khai toString của lớp thực tế ở thời điểm chạy. Quy tắc chọn phương thức được xác định trong [JLS 21, mục 15.12.2](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12.2).

Với mảng int[], không có phiên bản append(int[]). Dùng Arrays.toString(numbers) khi muốn dạng danh sách phần tử. Với mảng nhiều chiều, có thể cần Arrays.deepToString theo cấu trúc dữ liệu.

Đừng dựa vào số ký tự hoặc hậu tố của biểu diễn mặc định của mảng; nó không phải nội dung mảng và không có giá trị cố định giữa các lần chạy.

### Phạm vi char[] dùng số lượng, không phải vị trí kết thúc

```java
char[] letters = {'W', 'X', 'Y', 'Z'};
StringBuilder result = new StringBuilder();
result.append(letters, 1, 2);
// Bat dau tai chi so 1, lay 2 phan tu -> "XY".
```

Phân biệt:

- append(CharSequence, start, end): lấy đoạn [start, end).
- append(char[], offset, len): lấy len phần tử từ offset.

Hai chữ ký đều có ba tham số nhưng tham số cuối mang ý nghĩa khác nhau.

## 6. null phải được hiểu theo phiên bản được chọn

| Lời gọi | Hành vi |
| --- | --- |
| append((String) null) | Thêm bốn ký tự null |
| append((Object) null) | Thêm bốn ký tự null |
| append((CharSequence) null) | Thêm bốn ký tự null |
| append((char[]) null) | Gây NullPointerException |
| append(null) không chỉ rõ kiểu | Có thể không biên dịch vì các phiên bản tham chiếu không có lựa chọn cụ thể nhất |

Với StringBuilder, lời gọi trần append(null) là mơ hồ giữa các phiên bản tham chiếu phù hợp, nên trình biên dịch từ chối. Không được suy luận “null luôn gây NullPointerException” hoặc “null luôn được thêm thành chữ null”.

Có thể viết một lời gọi có kiểu rõ ràng, nhưng ứng dụng vẫn phải quyết định **có muốn hiển thị chữ null hay không**:

```java
String displayName = null;
StringBuilder message = new StringBuilder();
message.append("name=").append(displayName == null ? "(missing)" : displayName);
// "name=(missing)"
```

Nếu trường bắt buộc không được thiếu, báo lỗi trước khi xây dựng thông báo có thể phù hợp hơn việc tự thay bằng một nhãn.

## 7. Chương trình hoàn chỉnh và kết quả

Lưu **AppendDemo.java**. Chương trình dùng cú pháp và API có trên Java 17 trở lên.

```java
import java.util.Arrays;

public class AppendDemo {
    private static final class Product {
        private final String code;
        private final int stock;

        Product(String code, int stock) {
            this.code = code;
            this.stock = stock;
        }

        @Override
        public String toString() {
            return "Product{code=" + code + ", stock=" + stock + "}";
        }
    }

    public static void main(String[] args) {
        StringBuilder text = new StringBuilder();
        StringBuilder returned = text.append("Java").append(' ').append(21);
        System.out.println("text=[" + text + "]");
        System.out.println("same-builder=" + (returned == text));

        byte small = 7;
        short medium = 12;
        StringBuilder values = new StringBuilder();
        values.append(small).append(',').append(medium).append(',')
                .append(42).append(',').append(9000000000L).append(',')
                .append(1.5f).append(',').append(2.25d).append(',')
                .append(true).append(',').append('X');
        System.out.println("primitives=[" + values + "]");

        Product product = new Product("P01", 8);
        System.out.println("object=[" + new StringBuilder().append(product) + "]");

        StringBuilder source = new StringBuilder("draft");
        StringBuilder target = new StringBuilder().append(source);
        source.append("!");
        System.out.println("source=[" + source + "]");
        System.out.println("target=[" + target + "]");

        StringBuilder nulls = new StringBuilder();
        nulls.append((String) null).append('|')
                .append((Object) null).append('|')
                .append((CharSequence) null);
        System.out.println("nulls=[" + nulls + "]");

        try {
            new StringBuilder().append((char[]) null);
        } catch (NullPointerException ex) {
            System.out.println("null-char-array=" + ex.getClass().getSimpleName());
        }

        char[] letters = {'A', 'B', 'C'};
        int[] numbers = {1, 2, 3};
        System.out.println("chars=[" + new StringBuilder().append(letters) + "]");
        System.out.println("numbers=[" + new StringBuilder()
                .append(Arrays.toString(numbers)) + "]");
        System.out.println("ranges=[" + new StringBuilder()
                .append("ABCDE", 1, 3).append('|')
                .append(new char[]{'W', 'X', 'Y', 'Z'}, 1, 2) + "]");

        System.out.println("append-number=[" + new StringBuilder().append(65) + "]");
        System.out.println("append-character=[" + new StringBuilder().append('A') + "]");
        System.out.println("numeric-expression=[" + new StringBuilder().append('A' + 1) + "]");
        System.out.println("two-numbers=[" + new StringBuilder().append(1).append(2) + "]");
        System.out.println("sum=[" + new StringBuilder().append(1 + 2) + "]");
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 AppendDemo.java
java AppendDemo
```

Kết quả chuẩn:

```text
text=[Java 21]
same-builder=true
primitives=[7,12,42,9000000000,1.5,2.25,true,X]
object=[Product{code=P01, stock=8}]
source=[draft!]
target=[draft]
nulls=[null|null|null]
null-char-array=NullPointerException
chars=[ABC]
numbers=[[1, 2, 3]]
ranges=[BC|XY]
append-number=[65]
append-character=[A]
numeric-expression=[66]
two-numbers=[12]
sum=[3]
```

Ở dòng numbers, cặp ngoặc ngoài do chương trình in để đánh dấu kết quả; cặp ngoặc trong thuộc chuỗi "[1, 2, 3]" do Arrays.toString tạo.

same-builder=true xác nhận append trả chính đối tượng đang được sửa. Dòng target vẫn là draft xác nhận builder đích không theo dõi các thay đổi về sau của nguồn.

Các dòng cuối tách ba việc: thêm số, thêm ký tự và tính biểu thức trước khi thêm. Khi stdout khác dự đoán, hãy kiểm tra kiểu đối số và phép tính đã xảy ra trước lời gọi.

## 8. Cách viết append rõ ràng trong ứng dụng

### 8.1. Thêm từng thành phần thay vì dựng chuỗi trung gian không cần thiết

```java
StringBuilder line = new StringBuilder();
line.append("code=").append("P01").append(", stock=").append(8);
```

Cách này thể hiện trực tiếp các phần được thêm. Không cần ép từng số sang String hoặc dùng biểu thức nối bên trong mọi append.

Tuy nhiên, không có quy tắc phải thay mọi biểu thức nối ngắn bằng builder. Khi đang dùng builder để tích lũy nội dung, hãy tận dụng API theo cách dễ đọc; khi một biểu thức String ngắn đã rõ, không cần tạo thêm cấu trúc.

### 8.2. Dấu phân cách phải là một phần của thuật toán

append không tự chèn dấu cách, dấu phẩy hay xuống dòng. Khi duyệt nhiều phần tử, cần chủ động xác định vị trí dấu phân cách:

```java
StringBuilder line = new StringBuilder();
for (int i = 0; i < values.length; i++) {
    if (i > 0) {
        line.append(", ");
    }
    line.append(values[i]);
}
```

Đây là đoạn minh họa trong phương thức có mảng values. Với mảng String chỉ cần nối bằng một dấu phân cách cố định, String.join có thể diễn đạt ngắn hơn; builder hữu ích khi có thêm điều kiện hoặc nhiều kiểu dữ liệu.

### 8.3. Giữ builder trong một phạm vi sở hữu rõ ràng

append sửa trạng thái. Hai biến cùng tham chiếu một builder sẽ cùng thấy thay đổi. Nên tạo builder cục bộ khi xây một kết quả và trả toString khi hoàn tất, nếu bên ngoài chỉ cần giá trị văn bản.

StringBuilder không tự đồng bộ cho nhiều luồng cùng sửa. Các chuỗi append trong bài được hiểu là chạy tuần tự trong một luồng. Không chia sẻ một builder tĩnh cho nhiều yêu cầu chỉ để tránh tạo đối tượng mới.

## 9. Thực hành

1. Đổi append(65) thành appendCodePoint(65). Kết quả phải là A. Giải thích sự khác nhau về hợp đồng tham số.
2. Thay append(1).append(2) bằng append(1 + 2). Xác nhận kết quả từ "12" thành "3".
3. Tạo biến Object tham chiếu Product rồi append biến đó. toString của Product vẫn được gọi; giải thích vì sao điều này không mâu thuẫn với việc chữ ký append được chọn khi biên dịch.
4. Tạo char[] chứa A, B, C; append nó rồi đổi phần tử đầu của mảng thành Z. Builder đã nhận vẫn chứa ABC, không tự đổi theo mảng.
5. Thêm một trường String có thể null vào thông báo. Tự chọn quy tắc hiển thị trường thiếu và viết rõ quy tắc đó trước khi append.
6. Dùng hai phiên bản append theo phạm vi để cùng tạo chuỗi BC từ String "ABCDE" và char[] tương ứng. Xác định tham số cuối là end hay len ở từng lời gọi.

Sau bài này, cần giải thích được ba bước của một lời gọi: biểu thức đối số được tính thành giá trị nào, phiên bản append nào được chọn và biểu diễn nào được thêm vào builder. Ba câu trả lời đó giúp dự đoán nội dung chính xác.
