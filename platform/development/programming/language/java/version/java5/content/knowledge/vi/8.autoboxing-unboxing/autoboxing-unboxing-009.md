# Chuyển đổi kiểu trong biểu thức điều kiện ba ngôi

## 1. Chỉ một nhánh chạy, nhưng cả hai nhánh tham gia xác định kiểu

Toán tử điều kiện `?:` chọn một trong hai biểu thức theo điều kiện:

```java
boolean preferred = true;
int selected = preferred ? 10 : 20;
```

Nếu điều kiện là `true`, nhánh sau `?` được đánh giá; nếu là `false`, nhánh sau `:` được đánh giá. **Không phải cả hai nhánh đều chạy.**

Tuy nhiên, trình biên dịch cần xác định kiểu của **toàn bộ biểu thức** từ các kiểu nhánh và ngữ cảnh áp dụng. Giá trị của nhánh được chọn có thể phải unbox, nâng kiểu số hoặc box lại theo kiểu ấy trước khi được gán cho biến đích.

Vì vậy, không nên đọc `flag ? left : right` thành “lấy nguyên đối tượng ở một bên, luôn giữ nguyên kiểu của bên đó”. Điều này chỉ đúng trong những ngữ cảnh tham chiếu phù hợp, không đúng với mọi biểu thức số hoặc boolean.

Bài này dùng quy tắc hiện hành của Java và các ví dụ chạy được với Java 17 trở lên.

## 2. Điều kiện ở đầu có thể cần unboxing

Toán hạng trước `?` phải có kiểu `boolean` hoặc `Boolean` phù hợp. Nếu là `Boolean`, nó được unbox để quyết định nhánh:

```java
Boolean chooseLeft = null;
// int result = chooseLeft ? 1 : 2; // Gây NullPointerException khi chạy.
```

Lỗi phát sinh khi đánh giá điều kiện, trước khi chọn nhánh. Hai nhánh đều là số hợp lệ cũng không giúp một điều kiện `null` trở thành `false`.

Nếu nghiệp vụ chủ động coi “chưa có giá trị” là không chọn nhánh trái, có thể viết `Boolean.TRUE.equals(chooseLeft) ? 1 : 2`. Nếu `null` là dữ liệu sai, nên từ chối rõ ràng thay vì âm thầm gộp nó với `false`.

## 3. Phân loại theo hai nhánh kết quả

Java phân biệt ba nhóm biểu thức điều kiện:

| Nhóm | Các nhánh minh họa | Điều cần xét |
| --- | --- | --- |
| Boolean | `Boolean` với `boolean` | Có cần unbox về `boolean` không? |
| Số | `Integer` với `int`, hoặc `Integer` với `Long` | Kiểu số chung, các quy tắc đặc biệt và chuyển đổi boxing/unboxing |
| Tham chiếu | `String` với `Object`, hoặc một nhánh `null` phù hợp | Kiểu tham chiếu và ngữ cảnh đích có thể tham gia |

Đây là cách nhận biết các trường hợp trong bài, không phải một thuật toán thay thế toàn bộ đặc tả. Trong mã phức tạp, kiểu của lời gọi phương thức hoặc biểu thức lồng nhau cũng góp phần vào việc phân loại.

Các biểu thức điều kiện số và boolean có kiểu được xác định theo quy tắc riêng, không dùng kiểu biến đích để tùy ý thay đổi phép tính bên trong. Biểu thức điều kiện tham chiếu có thể sử dụng ngữ cảnh đích trong phép gán hoặc lời gọi phương thức.

## 4. Wrapper và primitive tương ứng dẫn tới primitive

```java
boolean chooseLeft = true;
Integer left = 7;
Integer result = chooseLeft ? left : 0;
```

Hai nhánh là `Integer` và `int`, nên biểu thức điều kiện số trong trường hợp này có kiểu `int`. Nếu nhánh trái được chọn, `left` phải được unbox. Khi gán kết quả cho `Integer result`, giá trị `int` lại được boxing.

```text
Integer left
    ↓ unboxing nếu chọn nhánh trái
int của biểu thức điều kiện
    ↓ boxing khi gán
Integer result
```

Kiểu `Integer` của biến nhận không loại bỏ bước unboxing ở giữa. Đây là nguồn lỗi khi nhánh wrapper có thể null:

```java
Integer left = null;
boolean chooseLeft = true;
// Integer result = chooseLeft ? left : 0; // NullPointerException.
```

Nếu `chooseLeft` là `false`, nhánh `left` không được đánh giá nên không unbox tham chiếu null đó; kết quả số `0` có thể được boxing cho biến đích. Lỗi phụ thuộc nhánh thật sự được chọn, còn yêu cầu chuyển đổi của nhánh đã được xác định từ kiểu của biểu thức.

## 5. Hai nhánh cùng wrapper có thể giữ tham chiếu null

```java
Integer left = null;
boolean chooseLeft = true;
Integer result = chooseLeft ? left : Integer.valueOf(0);
```

Hai nhánh cùng có kiểu `Integer`, nên kiểu của biểu thức là `Integer`. Với điều kiện trên, kết quả giữ `null`; không có bước bắt buộc unbox nhánh trái chỉ để tạo kết quả biểu thức.

Điều này không có nghĩa dữ liệu đã an toàn để tính toán. Nếu sau đó gán `int primitive = result`, unboxing lại xảy ra ở phép gán và gây lỗi nếu kết quả vẫn null.

Đối với boolean, quy tắc tương ứng là:

- Hai nhánh cùng `Boolean` cho kết quả kiểu `Boolean`.
- Các kết hợp boolean còn lại phù hợp trong nhóm này cho kiểu `boolean`, nên nhánh `Boolean` được chọn có thể phải unbox.

```java
Boolean optional = null;
boolean chooseLeft = true;
Boolean preserved = chooseLeft ? optional : Boolean.FALSE;
// Boolean converted = chooseLeft ? optional : false; // NullPointerException.
```

Dùng kiểu nhánh thống nhất chỉ là cách giữ đúng hợp đồng biểu thức mong muốn. Nó không thay thế việc xác định ý nghĩa của trạng thái thiếu dữ liệu.

## 6. Hai wrapper số khác nhau có thể làm đổi cả lớp kết quả

```java
boolean chooseLeft = true;
Integer small = 1;
Long large = 2L;
Number result = chooseLeft ? small : large;
```

Vì hai nhánh đều là biểu thức số, Java áp dụng quy tắc kiểu số cho toàn bộ biểu thức. `Integer` và `Long` được xem qua các giá trị `int` và `long`; kiểu số kết quả là `long`.

Khi chọn nhánh trái, giá trị `1` được unbox từ `Integer`, chuyển thành `long`, rồi boxing thành `Long` để gán cho `Number`. `result` vì thế giữ một đối tượng `Long`, không phải tham chiếu `Integer small` ban đầu.

Các trường hợp thường gặp:

| Kiểu nhánh trái và phải | Kiểu của biểu thức số trong trường hợp này |
| --- | --- |
| `Integer`, `Integer` | `Integer` |
| `Integer`, `int` | `int` |
| `Integer`, `Long` | `long` |
| `Integer`, `Double` | `double` |
| `Float`, `Double` | `double` |

Không suy ra rằng “chọn nhánh trái thì lúc nào cũng giữ lớp wrapper bên trái”. Một phép nâng kiểu số có thể thay đổi biểu diễn kết quả và trong một số tổ hợp có thể làm mất độ chính xác.

## 7. Quy tắc số nhỏ và hằng số không chỉ là chọn kiểu lớn nhất

Một số biểu thức số có quy tắc giữ kiểu nhỏ khi nhánh còn lại là hằng `int` biểu diễn được trong kiểu đó:

```java
boolean chooseLeft = true;
byte small = 5;
byte narrow = chooseLeft ? small : 10;
int wider = chooseLeft ? small : 1000;
```

Ở dòng đầu, `10` là hằng `int` nằm trong miền `byte`, nên biểu thức có thể giữ kiểu `byte`. `1000` không nằm trong miền ấy, nên trường hợp tiếp theo có kiểu `int`.

Các quy tắc tương tự có liên quan đến `byte`, `short`, `char` và wrapper tương ứng trong những tổ hợp được đặc tả quy định. Vì vậy, câu “toán tử ba ngôi luôn unbox rồi nâng mọi thứ lên ít nhất int” là quá đơn giản và có thể sai.

Khi kiểu kết quả ảnh hưởng tới overload, API hoặc khả năng giữ null, hãy tra đúng tổ hợp kiểu thay vì dựa vào kích thước số đang quan sát ở lần chạy hiện tại.

## 8. null literal khác với một biến wrapper đang chứa null

So sánh hai trường hợp:

```java
boolean chooseLeft = true;
Integer optional = null;
Integer literalNull = chooseLeft ? null : 0;
// Integer wrapperNull = chooseLeft ? optional : 0; // NullPointerException.
```

`null` literal không có kiểu `Integer`; nó có kiểu null đặc biệt. Trường hợp `null` và `int` được xử lý như biểu thức điều kiện tham chiếu, với ngữ cảnh đích phù hợp ở phép gán này. Nếu chọn `null`, kết quả có thể là tham chiếu null.

Ngược lại, biến `optional` có kiểu tĩnh `Integer`. Khi kết hợp với nhánh `int 0`, ta quay về trường hợp biểu thức số có kiểu `int` và cần unboxing nhánh wrapper được chọn.

Cùng là giá trị null khi chạy nhưng khác kiểu biểu thức lúc biên dịch có thể dẫn tới chuyển đổi khác nhau. Không thay một literal bằng một biến wrapper rồi giả định hợp đồng kiểu của toàn bộ biểu thức giữ nguyên.

## 9. Khi cần giữ chính tham chiếu của một nhánh

Nếu ý định là chọn một đối tượng số và giữ nguyên kiểu đối tượng được chọn, có thể diễn đạt theo ngữ cảnh tham chiếu:

```java
boolean chooseLeft = true;
Integer small = 1;
Long large = 2L;
Number kept = chooseLeft ? (Number) small : large;
```

Nhánh được cast sang `Number` khiến hai nhánh không còn tạo thành trường hợp điều kiện số `Integer`/`Long` như trước. Trong ngữ cảnh tham chiếu này, chọn nhánh trái giữ chính đối tượng `Integer` dưới hợp đồng `Number`.

Cast ở đây là mở rộng kiểu tham chiếu, không phải unboxing hay đổi số. Nếu cách biểu đạt vẫn khó đọc, tách thành hai phép gán:

```java
Number kept;
if (chooseLeft) {
    kept = small;
} else {
    kept = large;
}
```

Hai phép gán tới `Number` không tạo một phép nâng kiểu số chung như một biểu thức điều kiện số. Vì vậy, `if/else` và `?:` có thể cùng chọn nhánh về mặt logic nhưng không phải lúc nào cũng có cùng các chuyển đổi kiểu trung gian.

Không thêm cast một cách máy móc để che lỗi. Trước hết xác định API cần một giá trị số primitive chung hay cần giữ đối tượng tham chiếu được chọn.

## 10. Chương trình chạy đầy đủ

Lưu thành **`ConditionalConversionsDemo.java`**:

```java
public class ConditionalConversionsDemo {
    static String kind(int value) {
        return "int";
    }

    static String kind(Integer value) {
        return "Integer";
    }

    public static void main(String[] args) {
        boolean chooseLeft = true;
        Integer small = 1;
        Long large = 2L;

        Number numeric = chooseLeft ? small : large;
        Number reference = chooseLeft ? (Number) small : large;
        System.out.println("numeric class=" + numeric.getClass().getSimpleName());
        System.out.println("reference class=" + reference.getClass().getSimpleName());

        Integer optional = null;
        Integer literalNull = chooseLeft ? null : 0;
        Integer sameWrapper = chooseLeft ? optional : Integer.valueOf(0);
        System.out.println("literal null=" + literalNull);
        System.out.println("same wrapper=" + sameWrapper);

        try {
            Integer converted = chooseLeft ? optional : 0;
            System.out.println(converted);
        } catch (NullPointerException ex) {
            System.out.println("numeric null rejected");
        }

        Boolean optionalFlag = null;
        try {
            Boolean converted = chooseLeft ? optionalFlag : false;
            System.out.println(converted);
        } catch (NullPointerException ex) {
            System.out.println("boolean null rejected");
        }

        Boolean selector = null;
        try {
            int value = selector ? 1 : 2;
            System.out.println(value);
        } catch (NullPointerException ex) {
            System.out.println("condition null rejected");
        }

        int unselectedNull = false ? optional : 0;
        System.out.println("unselected null=" + unselectedNull);

        byte b = 5;
        byte narrow = chooseLeft ? b : 10;
        int wider = chooseLeft ? b : 1000;
        System.out.println("narrow=" + narrow + ", wider=" + wider);

        System.out.println("mixed overload=" + kind(chooseLeft ? small : 0));
        System.out.println("boxed overload="
                + kind(chooseLeft ? small : Integer.valueOf(0)));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all ConditionalConversionsDemo.java
java ConditionalConversionsDemo
```

Stdout chính xác:

```text
numeric class=Long
reference class=Integer
literal null=null
same wrapper=null
numeric null rejected
boolean null rejected
condition null rejected
unselected null=0
narrow=5, wider=5
mixed overload=int
boxed overload=Integer
```

Hai dòng overload cho thấy kiểu của toàn biểu thức ảnh hưởng tới phương thức được chọn tại thời điểm biên dịch. Một nhánh dùng `int 0` làm lời gọi phù hợp nhất với `kind(int)`; hai nhánh cùng `Integer` làm lời gọi phù hợp nhất với `kind(Integer)`.

Ba lỗi null trong chương trình được bắt có chủ đích để thấy chúng xuất hiện ở các bước khác nhau. Dòng `unselected null=0` chứng minh Java không đánh giá nhánh không được chọn, ngay cả khi nhánh ấy nếu được chọn sẽ cần unbox một tham chiếu null.

## 11. Cách đọc một biểu thức điều kiện trước khi sửa

1. Xác định kiểu của điều kiện trước `?`; nếu là `Boolean`, kiểm tra khả năng null ở chính điều kiện.
2. Xác định kiểu tĩnh của từng nhánh, phân biệt primitive, wrapper, một kiểu cha như `Number` và null literal.
3. Phân loại biểu thức boolean, số hay tham chiếu; với biểu thức số, xét cả các quy tắc đặc biệt về hằng số và kiểu nhỏ.
4. Đánh dấu chuyển đổi của nhánh được chọn: unboxing, nâng/hạ kiểu được phép, boxing hoặc mở rộng tham chiếu.
5. Sau đó mới xét chuyển đổi khi gán hoặc truyền kết quả vào phương thức khác.

Nếu biểu thức lồng nhiều tầng và chính sách null không rõ, dùng biến có kiểu rõ ràng hoặc `if/else` để thể hiện hợp đồng. Không giả định kiểu biến đích luôn quyết định kiểu trung gian của `?:`.

`?:` là biểu thức tạo giá trị, không phải thay thế mọi câu lệnh `if/else`. Chẳng hạn, không dùng hai lời gọi trả về `void` làm các nhánh chỉ để chọn thao tác in; dùng câu lệnh điều kiện sẽ đúng mục đích hơn.

## 12. Tự thực hành

1. Đổi `chooseLeft` thành `false` trong chương trình. Xác định những trường hợp null nào không còn bị chọn và những lỗi nào vẫn xuất phát từ điều kiện riêng.
2. Thay cặp `Integer`/`Long` bằng `Integer`/`Double`. Kiểm tra lớp đối tượng kết quả khi gán vào `Number` và giải thích các bước chuyển đổi.
3. So sánh `condition ? null : 0` với `condition ? nullableInteger : 0` khi điều kiện đúng. Giải thích bằng kiểu tĩnh của nhánh, không chỉ bằng giá trị null.
4. Đổi hằng `10` trong ví dụ `byte` thành một giá trị không biểu diễn được bằng `byte`; quan sát lỗi nếu vẫn cố gán kết quả vào biến `byte`.
5. Viết lại lựa chọn hai wrapper số bằng `if/else` để giữ tham chiếu ban đầu. Kiểm tra bằng `getClass()` với đầu vào khác null.

Khi dùng toán tử điều kiện, cần tách việc **chọn nhánh lúc chạy** khỏi việc **xác định kiểu lúc biên dịch**. Hai bước cùng tham gia vào kết quả cuối cùng; hiểu đúng chúng giúp tránh unboxing null, thay đổi lớp wrapper ngoài ý muốn và chọn nhầm overload.

## Tài liệu đối chiếu

- [JLS §15.25 — Conditional Operator](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.25): phân loại, xác định kiểu và đánh giá biểu thức điều kiện.
- [JLS §15.25.1 — Boolean Conditional Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.25.1): kết hợp `boolean` và `Boolean`.
- [JLS §15.25.2 — Numeric Conditional Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.25.2): wrapper số, primitive, hằng số và nâng kiểu.
- [JLS §15.25.3 — Reference Conditional Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.25.3): biểu thức tham chiếu và ngữ cảnh đích.
