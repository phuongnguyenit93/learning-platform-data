# Phân biệt remove(int) với remove(Object)

## 1. Một tên phương thức, hai ý định xóa khác nhau

Một `List` lưu phần tử theo vị trí. Vì vậy, có hai câu hỏi riêng biệt khi muốn xóa:

- “Xóa phần tử đang ở vị trí nào?”: dùng `remove(int index)`.
- “Xóa phần tử có giá trị bằng đối tượng nào?”: dùng `remove(Object o)`.

Đây là hai phương thức nạp chồng (overload): cùng tên `remove` nhưng khác kiểu tham số. Java không xem nội dung danh sách rồi đoán ý định của người viết. Trình biên dịch chọn phương thức từ kiểu của biểu thức gọi và kiểu của đối số.

Ví dụ, danh sách số nguyên `[10, 20, 10, 30]` có thể được nhìn theo hai hàng thông tin:

| Chỉ số | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| Giá trị | 10 | 20 | 10 | 30 |

`remove(1)` xóa phần tử ở chỉ số 1, tức giá trị 20. Muốn xóa giá trị 10 đầu tiên, viết `remove(Integer.valueOf(10))`. Hai lời gọi này khác nhau ngay cả khi cùng thao tác trên một đối tượng `ArrayList<Integer>`.

Nguy cơ lớn nhất xuất hiện với `List<Integer>`: cả chỉ số và giá trị đều trông giống số nguyên, nên một lời gọi vẫn biên dịch thành công nhưng thực hiện sai điều người viết mong muốn.

## 2. Hợp đồng của từng phương thức

| Thuộc tính | `E remove(int index)` | `boolean remove(Object o)` |
|---|---|---|
| Ý nghĩa đối số | Chỉ số của phần tử cần xóa | Đối tượng dùng để tìm phần tử bằng nó |
| Cách xác định phần tử | Vị trí tính từ 0 | Vị trí đầu tiên thỏa điều kiện bằng nhau |
| Kết quả trả về | Chính phần tử vừa xóa, có kiểu `E` | `true` nếu đã xóa được một phần tử; `false` nếu không tìm thấy |
| Số phần tử bị xóa trong một lời gọi thành công | Một | Một, kể cả khi có nhiều giá trị bằng nhau |
| Khi không có mục tiêu | Chỉ số ngoài phạm vi gây `IndexOutOfBoundsException` | Thường trả `false` khi đối tượng hợp lệ nhưng không có trong danh sách |
| Tác động đến vị trí còn lại | Các phần tử sau vị trí bị xóa chuyển sang chỉ số nhỏ hơn một | Tương tự, sau khi tìm và xóa phần tử đầu tiên phù hợp |

Với xóa theo chỉ số, điều kiện hợp lệ là `0 <= index && index < list.size()`. Chỉ số bằng `size()` không hợp lệ. Đừng áp dụng nhầm quy tắc chèn của `add(index, element)`, vốn có thể cho phép chèn ở cuối.

Với xóa theo đối tượng, hợp đồng của `List` mô tả việc xóa phần tử có chỉ số nhỏ nhất thỏa `Objects.equals(o, get(i))`, nếu tồn tại. Nó dùng quan hệ bằng nhau, không dùng “cùng đối tượng trong bộ nhớ” làm tiêu chuẩn chung. `remove(Object)` cũng không có nghĩa là xóa tất cả phần tử trùng giá trị.

Cả hai là thao tác sửa đổi tùy chọn. Danh sách không hỗ trợ xóa có thể ném `UnsupportedOperationException`. Với `remove(Object)`, một số triển khai còn có thể từ chối kiểu đối số không hợp lệ hoặc `null` bằng ngoại lệ theo hợp đồng API. Không khái quát kết quả của một `ArrayList` thành mọi triển khai `List`. [Hợp đồng List.remove](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#remove(int)), [List.remove(Object)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#remove(java.lang.Object)).

## 3. Vì sao int và Integer chọn hai overload khác nhau?

### 3.1. Đối số int chọn xóa theo chỉ số

Đoạn sau minh họa bên trong một phương thức:

```java
List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));

Integer removed = numbers.remove(1);

// removed = 20
// numbers = [10, 30]
```

Literal `1` có kiểu `int`. Với đối số này, `remove(int)` khớp trực tiếp. Mặc dù Java có thể boxing số nguyên thành `Integer` để truyền vào tham số `Object`, trình biên dịch không cần đến phép chuyển đổi đó khi đã có phương thức phù hợp ở giai đoạn trước.

Đừng đọc `numbers.remove(1)` thành “xóa số 1” chỉ vì `numbers` chứa `Integer`. Trong lời gọi này, số 1 là chỉ số.

### 3.2. Đối số Integer chọn xóa theo đối tượng

```java
List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));
Integer value = 20;

boolean removed = numbers.remove(value);

// removed = true
// numbers = [10, 30]
```

Đối số `value` có kiểu `Integer`. Nó có thể được chuyển rộng tham chiếu sang `Object` mà không cần unboxing. Phương thức `remove(Object)` vì vậy phù hợp ở giai đoạn gọi nghiêm ngặt. Phương án unboxing `Integer` thành `int` thuộc giai đoạn gọi có cho phép chuyển đổi bổ sung; Java không chuyển sang giai đoạn đó khi đã tìm được phương thức phù hợp trước đó.

Cách giải thích chính xác không phải là “Java luôn ưu tiên kiểu nguyên thủy” hay “Java luôn ưu tiên kiểu bao”. Cần nhìn kiểu đối số và các giai đoạn xác định phương thức áp dụng được. [JLS 15.12.2 về lựa chọn phương thức](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.2), [JLS 5.3 về chuyển đổi khi gọi phương thức](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.3).

### 3.3. Viết rõ ý định với List<Integer>

Nếu giá trị cần tìm đang là `int`, dùng `Integer.valueOf(value)` để xóa theo giá trị:

```java
List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));
int valueToDelete = 20;

boolean found = numbers.remove(Integer.valueOf(valueToDelete));
```

`Integer.valueOf` tạo hoặc cung cấp đối tượng bao mang giá trị đó. Việc có thể tái sử dụng đối tượng trong bộ nhớ đệm không quyết định kết quả xóa; `remove(Object)` dựa trên phép so sánh bằng nhau.

Nếu một biến `Integer` thực sự biểu diễn chỉ số, có thể chuyển rõ sang `int`:

```java
List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));
Integer index = 1;

Integer deleted = numbers.remove(index.intValue());
```

Chỉ làm điều này khi biến thực sự mang ý nghĩa vị trí, đồng thời xử lý khả năng `index == null` nếu đầu vào cho phép `null`. Đổi kiểu để ép một overload không thay cho việc xác định đúng ý nghĩa dữ liệu. [Integer.valueOf(int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html#valueOf(int)).

### 3.4. Bảng đọc nhanh đối số

Bảng dưới giả sử biến nhận có kiểu khai báo `List<Integer>`, đối tượng thực tế là `ArrayList<Integer>`, và các biến không phải `null` trừ hàng ghi rõ:

| Biểu thức gọi | Kiểu đối số | Overload được chọn | Ý nghĩa |
|---|---|---|---|
| `list.remove(1)` | `int` | `remove(int)` | Xóa chỉ số 1 |
| `list.remove(intValue)` | `int` | `remove(int)` | Xóa chỉ số có trong biến |
| `list.remove(Integer.valueOf(1))` | `Integer` | `remove(Object)` | Xóa giá trị `Integer` bằng 1 đầu tiên |
| `list.remove(integerValue)` | `Integer` | `remove(Object)` | Tìm theo giá trị của đối tượng |
| `list.remove(integerValue.intValue())` | `int` | `remove(int)` | Xóa theo chỉ số sau khi unboxing tường minh |
| `list.remove((int) integerValue)` | `int` | `remove(int)` | Cũng là xóa theo chỉ số; có thể lỗi nếu biến là `null` |
| `list.remove((Object) 1)` | `Object` | `remove(Object)` | Số 1 được boxing thành `Integer`, rồi dùng làm giá trị tìm |
| `list.remove(1L)` | `long` | `remove(Object)` | Boxing thành `Long`; không xóa số `Integer` bằng 1 trong `ArrayList<Integer>` |
| `list.remove(null)` | Kiểu null | `remove(Object)` | Tìm phần tử `null`, nếu triển khai cho phép |
| `list.remove((Integer) null)` | `Integer` | `remove(Object)` | Cũng tìm theo đối tượng; không unboxing tại lời gọi này |

Các đối số `byte`, `short`, `char` có thể được chuyển rộng thành `int`, nên khi gọi qua `List`, chúng chọn `remove(int)`. Ví dụ, một `char` có giá trị `'A'` sẽ được xem như chỉ số số học 65, không phải ký tự cần tìm. Với `List<Character>`, muốn xóa ký tự, truyền một `Character`, chẳng hạn `Character.valueOf('A')`.

Ngược lại, `long` không được tự thu hẹp thành `int` trong lời gọi này. `remove(1L)` vẫn có thể biên dịch vì `Long` là một `Object`. `Integer.valueOf(1).equals(Long.valueOf(1L))` là `false`, dù hai số có cùng giá trị toán học. Kiểu tham số là `Object` cũng có nghĩa rằng tham số kiểu `E = Integer` không bảo đảm mọi đối số truyền vào `remove(Object)` đều là `Integer`.

Với `var`, kiểu vẫn được suy luận lúc biên dịch: `var x = 1;` tạo biến `int`, còn `var x = Integer.valueOf(1);` tạo biến `Integer`. `var` không làm mất sự khác biệt giữa hai trường hợp.

## 4. Kiểu khai báo của biến nhận cũng quan trọng

`List` bổ sung thao tác xóa theo vị trí; giao diện `Collection` có `remove(Object)` nhưng không có `remove(int)`.

Đoạn minh họa:

```java
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));
Collection<Integer> view = numbers;

boolean removed = view.remove(1);

// removed = true
// numbers = [2, 3]
```

Qua biến `view` có kiểu `Collection<Integer>`, trình biên dịch chỉ thấy phương thức xóa theo đối tượng. Đối số `int` được boxing thành `Integer`, rồi dùng làm đối tượng tìm. Kết quả là xóa giá trị 1.

Nếu gọi `numbers.remove(1)` trên một danh sách ban đầu khác cũng chứa `[1, 2, 3]`, phương thức được chọn là xóa theo chỉ số và kết quả là `[1, 3]`.

`view` và `numbers` trong ví dụ cùng tham chiếu đến một đối tượng; không có bản sao danh sách nào được tạo khi gán `view = numbers`. Khác biệt nằm ở tập phương thức nhìn thấy tại chỗ gọi. Sau khi overload đã được chọn lúc biên dịch, cơ chế gọi phương thức của đối tượng thực tế mới thực thi phương thức tương ứng. Kiểu thực tế `ArrayList` không tự chọn lại giữa “chỉ số” và “giá trị” lúc chạy. [Collection.remove(Object)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#remove(java.lang.Object)).

Không nên đổi kiểu biến sang `Collection` chỉ để che một overload trong một đoạn mã khó hiểu. Hãy chọn giao diện theo nhu cầu của API, và diễn đạt rõ thao tác xóa giá trị khi đang làm việc với `List<Integer>`.

## 5. Kiểu kết quả nhận về không sửa được một lời gọi sai

Đoạn dưới cố ý không biên dịch:

```java
List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));

boolean removed = numbers.remove(1);
```

`remove(1)` vẫn được chọn là `remove(int)` và trả `Integer`. Java không nhìn biến đích `boolean` rồi quay lại chọn `remove(Object)`.

Sửa theo đúng ý định:

```java
// Muốn xóa giá trị 1:
boolean found = numbers.remove(Integer.valueOf(1));

// Muốn xóa phần tử tại chỉ số 1:
Integer deleted = numbers.remove(1);
```

Trong trường hợp đầu, `false` nghĩa là không tìm thấy giá trị 1. Trong trường hợp sau, kết quả là phần tử bị xóa, không phải cờ thành công. Phân biệt hai dạng kết quả cũng giúp người đọc phát hiện thao tác xóa bị viết nhầm.

Nếu không sử dụng kết quả trả về, nguy cơ lỗi kín càng lớn: `numbers.remove(1);` có thể biên dịch và chạy bình thường, nhưng đã xóa nhầm vị trí. Vì thế, đừng dùng tiêu chí “không báo lỗi biên dịch” để kết luận rằng ý định xóa đã được diễn đạt đúng.

## 6. Chương trình chạy đầy đủ: kiểm chứng lựa chọn overload

Các ví dụ ngắn phía trên minh họa thân một phương thức và cần các import thích hợp. Chương trình sau là tệp độc lập, dùng API có trong Java 17.

Lưu thành `RemoveOverloadDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class RemoveOverloadDemo {
    private static ArrayList<Integer> numbers() {
        return new ArrayList<>(List.of(10, 20, 10, 30));
    }

    public static void main(String[] args) {
        ArrayList<Integer> byIndex = numbers();
        Integer removedElement = byIndex.remove(1);
        System.out.println("remove(1) -> " + removedElement);
        System.out.println("byIndex = " + byIndex);

        ArrayList<Integer> byValue = numbers();
        boolean removedValue = byValue.remove(Integer.valueOf(10));
        System.out.println("remove(Integer.valueOf(10)) -> " + removedValue);
        System.out.println("byValue = " + byValue);

        ArrayList<Integer> primitiveArgument =
                new ArrayList<>(List.of(1, 2, 3));
        int index = 1;
        System.out.println("int argument -> " + primitiveArgument.remove(index));
        System.out.println("primitiveArgument = " + primitiveArgument);

        ArrayList<Integer> wrapperArgument =
                new ArrayList<>(List.of(1, 2, 3));
        Integer value = 1;
        System.out.println("Integer argument -> " + wrapperArgument.remove(value));
        System.out.println("wrapperArgument = " + wrapperArgument);

        ArrayList<Integer> differentWrapper =
                new ArrayList<>(List.of(1, 2, 3));
        System.out.println("long argument -> " + differentWrapper.remove(1L));
        System.out.println("differentWrapper = " + differentWrapper);

        List<Integer> backingList = new ArrayList<>(List.of(1, 2, 3));
        Collection<Integer> collectionView = backingList;
        System.out.println("Collection receiver -> " + collectionView.remove(1));
        System.out.println("backingList = " + backingList);

        List<String> words = new ArrayList<>(List.of("A", "B", "C"));
        System.out.println("String list, int argument -> " + words.remove(1));
        System.out.println("words = " + words);
        System.out.println("String list, String argument -> " + words.remove("C"));
        System.out.println("words = " + words);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 RemoveOverloadDemo.java
java RemoveOverloadDemo
```

Kết quả chuẩn:

```text
remove(1) -> 20
byIndex = [10, 10, 30]
remove(Integer.valueOf(10)) -> true
byValue = [20, 10, 30]
int argument -> 2
primitiveArgument = [1, 3]
Integer argument -> true
wrapperArgument = [2, 3]
long argument -> false
differentWrapper = [1, 2, 3]
Collection receiver -> true
backingList = [2, 3]
String list, int argument -> B
words = [A, C]
String list, String argument -> true
words = [A]
```

Đọc kết quả theo từng quyết định:

- `remove(1)` trên `[10, 20, 10, 30]` trả phần tử 20; hai giá trị 10 vẫn còn.
- `remove(Integer.valueOf(10))` trả `true` và chỉ xóa giá trị 10 đầu tiên; giá trị 10 còn lại vẫn giữ thứ tự tương đối với các phần tử khác.
- Hai biến cùng biểu diễn số 1 nhưng có kiểu `int` và `Integer` khiến lời gọi xóa hai phần tử khác nhau trên `[1, 2, 3]`.
- Đối số `1L` được xem là đối tượng `Long`; `ArrayList<Integer>` trong ví dụ không tìm thấy phần tử bằng nó nên trả `false`.
- Lời gọi qua `Collection<Integer>` xóa giá trị 1 trong chính danh sách gốc.
- Ngay cả `List<String>` vẫn có cả hai phương thức: truyền `1` xóa phần tử chỉ số 1, truyền `"C"` tìm chuỗi bằng `"C"`. Bẫy không chỉ tồn tại vì danh sách chứa số; danh sách số chỉ khiến nó khó nhận ra hơn.

## 7. Bằng nhau, phần tử trùng và vị trí sau khi xóa

### 7.1. Xóa theo đối tượng không phải xóa theo định danh trong bộ nhớ

Với các lớp có `equals` dựa trên nội dung như `String` và `Integer`, một đối tượng khác nhưng bằng nhau vẫn có thể làm đối số xóa.

Đoạn minh họa:

```java
List<String> labels = new ArrayList<>(List.of("java", "sql", "java"));

boolean changed = labels.remove(new String("java"));

// changed = true
// labels = [sql, java]
```

`new String("java")` không phải chính tham chiếu `String` đang lưu ở vị trí đầu, nhưng nó bằng chuỗi đó theo `equals`. Tạo `new String` ở đây chỉ để làm rõ cơ chế; trong mã thông thường, dùng literal `"java"` là đủ.

Với kiểu miền nghiệp vụ tự định nghĩa, cần biết hợp đồng `equals` của kiểu đó. Nếu lớp giữ cách so sánh tham chiếu kế thừa từ `Object`, một đối tượng mới chứa các trường trông giống nhau chưa chắc bằng đối tượng đang có trong danh sách. Đổi từ `remove(int)` sang `remove(Object)` không tự tạo ra quy tắc “trùng mã thì bằng nhau”.

### 7.2. Chỉ phần tử phù hợp đầu tiên bị xóa

Từ `[10, 20, 10, 30]`, xóa theo giá trị 10 một lần cho `[20, 10, 30]`. Nếu mục tiêu nghiệp vụ là “xóa mọi giá trị 10”, một lần gọi `remove(Object)` không đáp ứng mục tiêu đó. `removeIf` là API khác dành cho xóa theo điều kiện; cần xem hợp đồng riêng trước khi dùng, không gán ý nghĩa đó cho `remove(Object)`.

Sau một lần xóa, thứ tự tương đối của phần tử còn lại được bảo toàn, nhưng chỉ số thay đổi. Ví dụ, từ `[A, B, C, D]`, `remove(1)` tạo `[A, C, D]`. Nếu tiếp tục `remove(2)`, phần tử bị xóa là `D`, vì `C` đã chuyển sang chỉ số 1. Một chỉ số cũ không phải danh tính bền vững của phần tử.

Không sửa bằng cách thay máy móc `remove(index)` thành `remove(Integer.valueOf(index))`. Hai dòng diễn đạt hai ý định khác nhau; cần xác định đang giữ vị trí hay giữ giá trị.

## 8. null: phân biệt đối số null và kết quả null

`ArrayList` cho phép chứa `null`. Các tình huống sau vì vậy có thể xảy ra:

1. `list.remove(null)` hoặc `list.remove(nullableInteger)`, với `nullableInteger` có kiểu `Integer`, chọn `remove(Object)`. Nếu danh sách có `null`, nó xóa lần xuất hiện đầu tiên và trả `true`; lời gọi này không cần unboxing đối số.
2. `list.remove(index)` chọn xóa theo chỉ số. Nếu phần tử tại vị trí đó là `null`, phương thức xóa thành công và trả `null`.
3. Nếu gán kết quả `null` đó vào biến `int`, unboxing gây `NullPointerException` sau khi danh sách đã bị thay đổi.
4. Nếu gọi `nullableIndex.intValue()` khi biến chỉ số đang là `null`, lỗi xảy ra khi tính đối số, trước khi phương thức `remove` được gọi. Danh sách chưa bị xóa bởi lời gọi đó.

Hai lỗi `NullPointerException` ở mục 3 và 4 có cùng tên nhưng khác thời điểm và khác trạng thái danh sách sau lỗi. Bắt ngoại lệ không tự hoàn tác thao tác xóa đã thực hiện. [ArrayList và khả năng lưu null](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html), [JLS 5.1.8 về unboxing](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.8).

Chương trình độc lập dưới đây cũng kiểm tra chỉ số sai và danh sách không cho phép sửa đổi. Lưu thành `RemoveNullAndBoundaryDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class RemoveNullAndBoundaryDemo {
    public static void main(String[] args) {
        List<Integer> byValue =
                new ArrayList<>(Arrays.asList(7, null, 9, null));
        Integer nullableValue = null;
        System.out.println("remove nullable value -> " + byValue.remove(nullableValue));
        System.out.println("byValue = " + byValue);

        List<Integer> nullableResult =
                new ArrayList<>(Arrays.asList((Integer) null, 7));
        Integer removed = nullableResult.remove(0);
        System.out.println("removed element = " + removed);
        System.out.println("nullableResult = " + nullableResult);

        List<Integer> unboxAfter =
                new ArrayList<>(Arrays.asList(7, null, 9));
        try {
            int result = unboxAfter.remove(1);
            System.out.println("result = " + result);
        } catch (NullPointerException ex) {
            System.out.println("unbox returned null -> NullPointerException");
        }
        System.out.println("unboxAfter = " + unboxAfter);

        List<Integer> unboxBefore =
                new ArrayList<>(Arrays.asList(7, null, 9));
        Integer nullableIndex = null;
        try {
            unboxBefore.remove(nullableIndex.intValue());
        } catch (NullPointerException ex) {
            System.out.println("unbox argument null -> NullPointerException");
        }
        System.out.println("unboxBefore = " + unboxBefore);

        List<Integer> boundaries = new ArrayList<>(List.of(4, 5));
        System.out.println("missing value -> "
                + boundaries.remove(Integer.valueOf(-1)));
        try {
            boundaries.remove(-1);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("negative index -> IndexOutOfBoundsException");
        }
        try {
            boundaries.remove(boundaries.size());
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("index equal to size -> IndexOutOfBoundsException");
        }
        System.out.println("boundaries = " + boundaries);

        List<Integer> fixed = List.of(1, 2, 3);
        try {
            fixed.remove(Integer.valueOf(1));
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable list -> UnsupportedOperationException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 RemoveNullAndBoundaryDemo.java
java RemoveNullAndBoundaryDemo
```

Kết quả chuẩn:

```text
remove nullable value -> true
byValue = [7, 9, null]
removed element = null
nullableResult = [7]
unbox returned null -> NullPointerException
unboxAfter = [7, 9]
unbox argument null -> NullPointerException
unboxBefore = [7, null, 9]
missing value -> false
negative index -> IndexOutOfBoundsException
index equal to size -> IndexOutOfBoundsException
boundaries = [4, 5]
unmodifiable list -> UnsupportedOperationException
```

Các điểm cần đọc từ trạng thái sau thao tác:

- `byValue` ban đầu có hai `null`; sau `remove(nullableValue)` vẫn còn một `null`.
- `nullableResult.remove(0)` trả `null` hợp lệ khi nhận vào biến `Integer`.
- `unboxAfter` mất phần tử `null` dù lệnh gán vào `int` kết thúc bằng ngoại lệ.
- `unboxBefore` giữ nguyên vì `nullableIndex.intValue()` đã lỗi trước khi gọi `remove`.
- `Integer.valueOf(-1)` là đối tượng tìm; không tìm thấy thì trả `false`. Đối số `int` bằng -1 lại là chỉ số sai và gây ngoại lệ.
- Chỉ số bằng `size()` nằm ngay sau phần tử cuối, nên không có phần tử để xóa.
- `List.of` tạo danh sách không sửa đổi được. Dù đã chọn đúng overload xóa theo giá trị, việc xóa phần tử hiện có vẫn gây `UnsupportedOperationException`. Chọn đúng overload và có quyền sửa danh sách là hai điều kiện riêng.

Danh sách có kích thước cố định tạo bởi `Arrays.asList` cũng không hỗ trợ xóa phần tử. Trong chương trình, `Arrays.asList` được bọc bằng `new ArrayList<>(...)` để có danh sách cho phép xóa và đồng thời khởi tạo được các phần tử `null`.

## 9. Áp dụng trong mã thực tế

### 9.1. Tách ý nghĩa “mã phần tử” khỏi “vị trí hiển thị”

Giả sử hệ thống đang có `List<Integer> userIds`. Biến `selectedUserId` chứa mã người dùng, không phải số thứ tự trên giao diện.

Đoạn minh họa bên trong một phương thức:

```java
List<Integer> userIds = new ArrayList<>(List.of(101, 205, 309));
int selectedUserId = 205;

boolean deleted = userIds.remove(Integer.valueOf(selectedUserId));
```

Nếu viết `userIds.remove(selectedUserId)`, Java xem 205 là chỉ số và thường gây `IndexOutOfBoundsException`. Nguy hiểm hơn, với mã nhỏ như 1 trên danh sách đủ dài, thao tác có thể xóa nhầm người dùng mà không báo lỗi.

Ngược lại, nếu giao diện cung cấp chỉ số hàng đang chọn, hãy dùng `remove(selectedIndex)` sau khi kiểm tra đầu vào và xác định danh sách tại thời điểm xóa. Đừng boxing một chỉ số rồi vô tình chuyển thành tìm theo giá trị.

Tên biến nên biểu đạt ý nghĩa như `index`, `position`, `userId`, `valueToDelete`, thay vì một tên số chung chung. Khi sửa mã, cần kiểm tra cả nơi tạo ra biến, không chỉ kiểu của biến tại lời gọi.

### 9.2. API nội bộ có thể đặt tên rõ hơn

Khi một lớp tiện ích thực sự cần cung cấp cả hai ý định cho danh sách số, có thể đặt hai tên riêng thay vì tiếp tục tạo thêm một cặp overload khó đọc. Đây là các phương thức minh họa để đặt trong một lớp, không phải một chương trình độc lập:

```java
static Integer removeAt(List<Integer> numbers, int index) {
    return numbers.remove(index);
}

static boolean removeValue(List<Integer> numbers, int value) {
    return numbers.remove(Integer.valueOf(value));
}
```

`removeAt(numbers, 1)` và `removeValue(numbers, 1)` buộc ý nghĩa xuất hiện ngay tại chỗ gọi. Không cần tạo lớp tiện ích chỉ cho mọi lời gọi đơn lẻ; mục đích là giữ ngữ nghĩa rõ khi thiết kế API có nguy cơ nhầm lẫn.

### 9.3. Đừng suy luận hiệu năng chỉ từ tên overload

`remove(Object)` thường phải tìm phần tử phù hợp trước khi xóa. `remove(int)` đã nhận vị trí nhưng chi phí đến vị trí và cập nhật cấu trúc phụ thuộc triển khai.

Với `ArrayList`, xóa theo vị trí còn có thể phải dịch nhiều phần tử phía sau; có sẵn chỉ số không làm mọi lần xóa thành thời gian hằng số. Với danh sách liên kết, việc đi đến một vị trí cũng có chi phí. Chọn thao tác theo ý nghĩa đúng trước, rồi đánh giá hiệu năng bằng cấu trúc dữ liệu và khối lượng công việc cụ thể. Không đổi sang xóa theo chỉ số chỉ để bỏ bước tìm kiếm nếu chưa biết đúng vị trí.

## 10. Lỗi phổ biến và cách tự kiểm tra

| Dấu hiệu | Nguyên nhân thường gặp | Cách sửa theo ý định |
|---|---|---|
| Muốn xóa số 1 nhưng phần tử thứ hai biến mất | Truyền literal `int` vào `List.remove` | Dùng `Integer.valueOf(1)` nếu 1 là giá trị cần tìm |
| Muốn xóa chỉ số trong biến `Integer` nhưng danh sách không đổi | `remove(Object)` đã được chọn và không tìm thấy giá trị bằng biến đó | Dùng kiểu `int` cho chỉ số hoặc chuyển rõ sau khi xử lý `null` |
| `boolean ok = list.remove(1)` không biên dịch | Phương thức được chọn trả phần tử `Integer` | Sửa đối số hoặc kiểu kết quả theo ý định, không dựa vào biến nhận để chọn overload |
| `remove(1L)` trả `false` trên `ArrayList<Integer>` | Đang tìm một `Long`, không phải một `Integer` | Chuẩn hóa đúng kiểu giá trị trước khi xóa; không ép kiểu thu hẹp tùy tiện |
| Một giá trị trùng vẫn còn | `remove(Object)` chỉ xóa lần xuất hiện đầu tiên | Xác định có cần xóa một phần tử hay mọi phần tử thỏa điều kiện |
| Bị lỗi `null` nhưng phần tử đã biến mất | Kết quả `Integer null` bị unboxing sau khi xóa theo chỉ số | Nhận kết quả bằng `Integer` và xử lý `null` phù hợp |
| Đúng đối số nhưng vẫn có `UnsupportedOperationException` | Danh sách không hỗ trợ xóa | Chọn cấu trúc cho phép sửa đổi khi yêu cầu nghiệp vụ cần xóa |
| Cùng dữ liệu nhưng gọi qua `Collection` cho kết quả khác | Tập overload tại chỗ gọi khác với `List` | Kiểm tra kiểu khai báo của biến nhận |

Khi đọc một lời gọi `remove`, tự kiểm tra theo thứ tự:

1. Biến nhận được khai báo là `List`, `Collection` hay kiểu khác?
2. Đối số có kiểu gì sau khi biểu thức được tính: `int`, `Integer`, `Object`, `long` hay kiểu khác?
3. Overload được chọn biểu đạt vị trí hay giá trị?
4. Kết quả mong đợi là phần tử bị xóa hay cờ tìm thấy?
5. Danh sách có cho phép xóa và có thể chứa `null` không?
6. Sau khi xóa, chỉ số và trạng thái danh sách thay đổi thế nào?

## 11. Tự dự đoán trước khi chạy

Mỗi câu dùng danh sách mới, độc lập với câu khác:

```java
List<Integer> values = new ArrayList<>(List.of(2, 0, 2, 4));
```

| Câu | Lời gọi | Cần dự đoán |
|---|---|---|
| A | `values.remove(2)` | Giá trị trả về và danh sách còn lại |
| B | `values.remove(Integer.valueOf(2))` | Cờ trả về và phần tử 2 nào bị xóa |
| C | `values.remove(2L)` | Có xóa được số 2 không? |
| D | `Integer target = 0; values.remove(target);` | Xóa chỉ số 0 hay giá trị 0? |
| E | `Collection<Integer> view = values; view.remove(2);` | Đối tượng nào bị thay đổi? |

Đáp án và lý do:

- A: trả `Integer` bằng 2 ở chỉ số 2; còn `[2, 0, 4]`.
- B: trả `true`; xóa số 2 tại chỉ số 0; còn `[0, 2, 4]`.
- C: trên `ArrayList<Integer>` này, trả `false`; vẫn `[2, 0, 2, 4]`, vì đối số là `Long`.
- D: chọn `remove(Object)`, trả `true`, xóa giá trị 0; còn `[2, 2, 4]`. Kiểu `Integer` của `target` là yếu tố quyết định.
- E: qua `Collection`, số 2 được boxing và dùng để tìm theo giá trị; trả `true`, danh sách `values` còn `[0, 2, 4]`. `view` là tham chiếu khác đến cùng đối tượng.

Kỹ năng cần hình thành là đọc ra đúng ý định từ kiểu của lời gọi: `remove(int)` trả phần tử tại một vị trí, còn `remove(Object)` báo việc xóa lần xuất hiện đầu tiên bằng một đối tượng tìm. Với danh sách số, hãy viết rõ sự chuyển đổi cần thiết ngay nơi gọi để giá trị không bị hiểu thành chỉ số.
