# Cơ chế duyệt mảng và cơ chế duyệt `Iterable`

## 1. Cùng cú pháp nhưng có hai cơ chế khác nhau

Hai vòng lặp sau có hình thức giống nhau:

```java
for (int value : new int[]{1, 2, 3}) {
    System.out.println(value);
}

for (int value : List.of(1, 2, 3)) {
    System.out.println(value);
}
```

Nhưng Java không triển khai cả hai bằng cùng một cách:

- Với mảng, vòng lặp giữ tham chiếu đến mảng rồi đi qua các chỉ số từ `0` đến trước `length`.
- Với một nguồn `Iterable`, vòng lặp lấy một `Iterator`, kiểm tra `hasNext()` rồi lấy phần tử bằng `next()`.

Mảng không cần thực hiện `Iterable` để dùng được với `for-each`. Đây là một nhánh được ngôn ngữ hỗ trợ riêng.

Quy tắc dịch tương đương được mô tả trong [JLS §14.14.2](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.14.2). Hiểu hai nhánh giúp giải thích việc đánh giá nguồn, thứ tự duyệt, thay đổi dữ liệu và các lời gọi phát sinh khi chạy.

## 2. Biểu thức nguồn được đánh giá một lần

Với:

```java
for (int value : createArray()) {
    System.out.println(value);
}
```

`createArray()` được gọi một lần khi bắt đầu vòng lặp, không phải một lần cho từng phần tử.

Tương tự:

```java
for (String value : createIterable()) {
    System.out.println(value);
}
```

`createIterable()` được gọi một lần; trên kết quả đó, vòng lặp lấy một iterator cho lượt duyệt.

Các đoạn này minh họa cách dùng với phương thức tạo nguồn tương ứng, không phải chương trình độc lập. Chương trình đầy đủ phía dưới có các hàm tạo nguồn và nhật ký lời gọi để kiểm chứng.

Nếu hàm tạo nguồn có tác dụng phụ, tác dụng phụ đó vẫn xảy ra khi bắt đầu vòng lặp, kể cả khi nguồn được tạo ra không có phần tử. Nguồn rỗng không giống nguồn `null`: rỗng cho phép kết thúc bình thường mà không chạy thân vòng lặp; nguồn `null` gây lỗi khi cơ chế duyệt truy cập nó.

## 3. Nhánh mảng: giữ tham chiếu và dùng chỉ số

Với mảng đã có:

```java
int[] values = {1, 2, 3};
for (int value : values) {
    System.out.println(value);
}
```

Có thể hiểu cơ chế tương đương ở mức mã nguồn như sau:

```java
int[] capturedArray = values;
for (int index = 0; index < capturedArray.length; index++) {
    int value = capturedArray[index];
    System.out.println(value);
}
```

Đây là cách diễn giải ngữ nghĩa. Tên biến phụ do trình biên dịch tạo không xung đột với biến của người dùng; mã lệnh thực tế có thể lưu cả độ dài mảng vào một biến phụ vì độ dài của cùng đối tượng mảng không đổi.

Những hệ quả quan trọng:

- Thứ tự là chỉ số tăng dần.
- Không gọi `iterator()`, `hasNext()` hoặc `next()` trên mảng.
- Không sao chép toàn bộ nội dung mảng để tạo một ảnh chụp.
- Biến vòng lặp nhận giá trị ở ô tương ứng, không phải quyền thay thế ô đó chỉ bằng cách gán lại biến.
- Nếu phần tử chưa duyệt của cùng mảng bị thay đổi trong luồng thực thi hiện tại, lượt sau đọc giá trị mới ở ô đó.

### Gán lại biến nguồn không đổi mảng đã được giữ

```java
int[] values = {1, 2};
for (int value : values) {
    values = new int[]{99};
    System.out.println(value);
}
```

Vòng lặp vẫn in `1` rồi `2`. Biến `values` được gán sang một mảng khác, nhưng tham chiếu mảng mà vòng lặp đã giữ lúc bắt đầu vẫn là mảng cũ.

Điều này khác với việc ghi `oldArray[1] = 20` trên chính mảng đang duyệt. Gán lại biến tham chiếu và sửa nội dung đối tượng là hai hành động khác nhau.

## 4. Nhánh `Iterable`: lấy một đối tượng quản lý lượt duyệt

`Iterable<T>` cung cấp khả năng lấy một `Iterator<T>`. Không bắt buộc nguồn phải là một `List` hoặc thậm chí phải lưu sẵn toàn bộ phần tử trong bộ nhớ.

Với:

```java
Iterable<String> values = List.of("A", "B");
for (String value : values) {
    System.out.println(value);
}
```

Có thể hiểu cách thực hiện tương đương cho ví dụ kiểu đơn giản này:

```java
Iterator<String> cursor = values.iterator();
while (cursor.hasNext()) {
    String value = cursor.next();
    System.out.println(value);
}
```

Các lời gọi có vai trò:

1. `iterator()`: lấy trạng thái của lượt duyệt.
2. `hasNext()`: kiểm tra còn phần tử tiếp theo hay không.
3. `next()`: lấy phần tử tiếp theo và tiến trạng thái duyệt.
4. Khởi tạo biến vòng lặp từ kết quả, với chuyển đổi kiểu phù hợp.
5. Chạy thân vòng lặp rồi kiểm tra tiếp.

Theo [Iterator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Iterator.html), gọi `next()` khi đã hết phần tử phải ném `NoSuchElementException`. Trong quá trình `for-each` kết thúc bình thường, phép kiểm tra `hasNext()` ngăn vòng lặp yêu cầu một phần tử sau điểm kết thúc.

Nếu duyệt hết `n` phần tử bình thường, phần điều khiển của vòng lặp gọi `next()` `n` lần và `hasNext()` `n + 1` lần. Đây là số lời gọi do vòng lặp điều khiển; bản thân một iterator cụ thể có thể có các thao tác nội bộ riêng. Nếu `break`, `return` hoặc ngoại lệ kết thúc sớm, không áp dụng máy móc số đếm của lượt duyệt hoàn chỉnh.

## 5. `Iterable` khác `Iterator`

| Khái niệm | Vai trò |
| --- | --- |
| `Iterable<T>` | Nguồn có thể cung cấp một lượt duyệt |
| `Iterator<T>` | Đối tượng giữ vị trí/trạng thái của một lượt duyệt cụ thể |
| Mảng | Nguồn được ngôn ngữ duyệt trực tiếp theo chỉ số |

Một biến có kiểu `Iterator<Integer>` không tự trở thành nguồn hợp lệ chỉ vì nó có `hasNext()` và `next()`:

```java
Iterator<Integer> cursor = List.of(1, 2).iterator();
// for (Integer value : cursor) { } // Lỗi: kiểu nguồn không phải mảng/Iterable.
```

Dùng vòng lặp tường minh khi đang có iterator:

```java
while (cursor.hasNext()) {
    Integer value = cursor.next();
    System.out.println(value);
}
```

Một lớp tự viết có thể thực hiện cả hai interface, nhưng phải xét kiểu tĩnh thực sự của biểu thức nguồn. Java không dùng cơ chế “thấy có phương thức tên `iterator` là chấp nhận” cho mọi đối tượng.

Tài liệu [Iterable](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Iterable.html) xác định chính interface cho phép đối tượng làm nguồn của enhanced `for`.

## 6. Thứ tự và khả năng lặp lại do nguồn quyết định

`for-each` không tự sắp xếp dữ liệu:

- Mảng theo chỉ số tăng dần.
- Một `List` theo thứ tự iterator của list.
- Một tập hợp có thứ tự theo hợp đồng của tập hợp đó.
- Một nguồn tự viết theo quy tắc mà iterator cung cấp.

Đừng thấy cú pháp giống nhau rồi suy ra mọi nguồn đều có cùng thứ tự hoặc đều có thể duyệt lại giống nhau.

Mỗi lần bắt đầu một vòng `for-each` trên `Iterable`, Java lại gọi `iterator()`. Một nguồn thông thường muốn hỗ trợ nhiều lượt độc lập sẽ tạo iterator mới với trạng thái riêng. Interface không tự đặt lại trạng thái nếu triển khai trả về cùng một iterator đã dùng hết hoặc phụ thuộc một nguồn dữ liệu chỉ đọc được một lượt.

Trong ví dụ cuối bài, `TraceRange.iterator()` tạo một đối tượng mới. Vì vậy, vị trí `nextValue` thuộc từng lượt duyệt, không dùng chung một biến vị trí cho mọi vòng lặp.

`for-each` cũng không tự tạo snapshot hay tự thêm đồng bộ hóa cho collection. Những chính sách về thay đổi cấu trúc trong lúc duyệt, quan sát dữ liệu đồng thời hoặc ảnh chụp thuộc hợp đồng của nguồn/iterator cụ thể. Không dùng riêng cú pháp vòng lặp làm bằng chứng rằng việc sửa nguồn là an toàn.

## 7. Một số giới hạn bắt nguồn từ kiểu của nguồn

### Mảng hỗ trợ `for-each` nhưng không phải `Iterable`

Một hàm nhận `Iterable<Integer>` không nhận trực tiếp `int[]` chỉ vì cả hai đều có thể xuất hiện sau dấu `:`:

```text
printValues(Iterable<Integer> values)
```

Chữ ký trên mô tả tham số của một hàm giả định. Muốn xử lý mảng bằng API nhận `Iterable`, cần một cách chuyển đổi/bao bọc có hợp đồng rõ, hoặc cung cấp đường xử lý mảng riêng.

### Kiểu tĩnh `Object` không đủ để duyệt mảng

```java
Object value = new int[]{1, 2};
// for (int element : value) { } // Lỗi biên dịch.
```

Đối tượng thực là mảng không thay thế được yêu cầu kiểu tĩnh của biểu thức nguồn. Cần kiểm tra hoặc giữ kiểu mảng phù hợp trước khi duyệt.

### `Arrays.asList(int[])` không biến từng số thành phần tử `Integer`

```java
int[] values = {7, 8};
List<int[]> wrapped = Arrays.asList(values);
System.out.println(wrapped.size()); // 1
```

Lời gọi này tạo cách nhìn danh sách có một phần tử là chính mảng `int[]`; không phải một `List<Integer>` có hai phần tử. `T` ở đây có thể là `int[]`, một kiểu tham chiếu.

Đây là hệ quả của chữ ký generic/varargs của [Arrays.asList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html#asList(T...)), không phải cơ chế `for-each` tự boxing toàn bộ mảng.

## 8. Chương trình hoàn chỉnh có nhật ký lời gọi

Lưu vào `ForEachMechanicsDemo.java`, dùng Java 17 trở lên:

```java
import java.util.Arrays;
import java.util.Iterator;
import java.util.NoSuchElementException;

public class ForEachMechanicsDemo {
    private static int arrayCalls;
    private static int[] backing;

    static int[] makeArray() {
        arrayCalls++;
        System.out.println("array source evaluated");
        backing = new int[]{1, 2, 3};
        return backing;
    }

    static Iterable<Integer> makeRange() {
        System.out.println("iterable source evaluated");
        return new TraceRange(4, 6);
    }

    static final class TraceRange implements Iterable<Integer> {
        private final int start;
        private final int end;

        TraceRange(int start, int end) {
            if (start > end) {
                throw new IllegalArgumentException("start must not exceed end");
            }
            this.start = start;
            this.end = end;
        }

        @Override
        public Iterator<Integer> iterator() {
            System.out.println("iterator() called");
            return new Iterator<>() {
                private int nextValue = start;

                @Override
                public boolean hasNext() {
                    boolean result = nextValue < end;
                    System.out.println("hasNext() -> " + result);
                    return result;
                }

                @Override
                public Integer next() {
                    if (nextValue >= end) {
                        throw new NoSuchElementException();
                    }
                    int result = nextValue++;
                    System.out.println("next() -> " + result);
                    return result;
                }
            };
        }
    }

    public static void main(String[] args) {
        for (int value : makeArray()) {
            if (value == 1) {
                backing[1] = 20;
                backing = new int[]{99};
            }
            System.out.println("array value = " + value);
        }
        System.out.println("array source calls = " + arrayCalls);
        System.out.println("backing variable now = " + Arrays.toString(backing));

        for (int value : makeRange()) {
            System.out.println("iterable body = " + value);
        }

        System.out.println("asList(int[]) size = " + Arrays.asList(new int[]{7, 8}).size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror -encoding UTF-8 ForEachMechanicsDemo.java
java ForEachMechanicsDemo
```

Kết quả chuẩn:

```text
array source evaluated
array value = 1
array value = 20
array value = 3
array source calls = 1
backing variable now = [99]
iterable source evaluated
iterator() called
hasNext() -> true
next() -> 4
iterable body = 4
hasNext() -> true
next() -> 5
iterable body = 5
hasNext() -> false
asList(int[]) size = 1
```

### Đọc phần mảng

`makeArray()` chỉ chạy một lần. Ở lượt đầu, chương trình sửa ô thứ hai của mảng cũ thành `20`, rồi gán biến `backing` sang mảng mới `[99]`.

Lượt sau vẫn đọc mảng cũ và nhận `20`, rồi `3`. Điều này đồng thời chứng minh:

- Vòng lặp giữ tham chiếu đến mảng ban đầu.
- Nó không chuyển sang mảng mới khi biến bên ngoài được gán lại.
- Nó không duyệt một bản sao nội dung bất biến được tạo từ lúc bắt đầu.

### Đọc phần `Iterable`

`makeRange()` được gọi một lần, `iterator()` một lần. Hai phần tử `4` và `5` có hai lời gọi `next()`; ba lần `hasNext()` gồm lần cuối cho `false`.

`TraceRange` không lưu một list gồm các số. Nó tính giá trị tiếp theo từ trạng thái iterator, cho thấy `Iterable` là giao thức duyệt, không phải lời hứa nguồn nhất thiết là một collection lưu sẵn.

Phương thức `next()` tự kiểm tra trạng thái hết dữ liệu mà không gọi `hasNext()` có nhật ký bên trong. Nhờ đó, log thể hiện rõ các lời gọi do vòng lặp tạo ra; một triển khai khác có thể tổ chức kiểm tra nội bộ khác mà vẫn đúng hợp đồng.

## 9. Quan sát hai nhánh trong bytecode

Chạy:

```shell
javap -c ForEachMechanicsDemo
```

Ở đoạn duyệt `int[]`, các lệnh chính có:

```text
arraylength
iaload
```

`arraylength` lấy độ dài mảng; `iaload` đọc phần tử `int` theo chỉ số. Không có iterator để điều khiển đoạn duyệt mảng đó.

Ở đoạn duyệt `Iterable<Integer>`, các lời gọi chính có dạng:

```text
Iterable.iterator:()Ljava/util/Iterator;
Iterator.hasNext:()Z
Iterator.next:()Ljava/lang/Object;
checkcast java/lang/Integer
Integer.intValue:()I
```

Sau `next()`, ví dụ cần dùng kết quả như `Integer`, rồi unboxing thành `int` cho biến vòng lặp. Đây là lý do có thể nhìn thấy cast và `intValue()` dù mã nguồn chỉ viết `for (int value : makeRange())`.

Các đoạn trên chỉ rút ra opcode/lời gọi quan trọng, không phải toàn bộ đầu ra nguyên văn. Offset và chỉ số constant pool không phải phần cần ghi nhớ.

Không kết luận hiệu năng chỉ bằng việc thấy một nhánh có iterator. JVM có thể tối ưu, và chi phí còn phụ thuộc nguồn, boxing, thân vòng lặp và dữ liệu thực. Dùng cơ chế để hiểu hành vi trước; đo lường phù hợp nếu cần so sánh hiệu năng.

## 10. Khi nên dùng dạng lặp tường minh

`for-each` phù hợp khi muốn xử lý từng phần tử theo thứ tự nguồn cung cấp và không cần truy cập cơ chế điều khiển.

Cân nhắc dạng khác khi:

- Cần chỉ số để thay phần tử trong mảng hoặc xử lý quan hệ giữa các vị trí.
- Đã có một `Iterator` và cần điều khiển trực tiếp nó.
- Cần thao tác như `Iterator.remove()` theo hợp đồng của nguồn; iterator ẩn của `for-each` không được đưa ra cho thân vòng lặp dùng.
- Nguồn có vòng đời tài nguyên cần được quản lý riêng; `for-each` không tự thay thế `try-with-resources`.

Đừng đổi mọi vòng lặp trên `List` thành `get(index)` chỉ để trông giống nhánh mảng. Với một cấu trúc truy cập theo chỉ số tốn thời gian như `LinkedList`, lặp bằng chỉ số có thể làm công việc đắt hơn nhiều so với iterator.

## 11. Tự kiểm tra

**Câu 1.** Duyệt `int[]` bằng `for-each` có gọi `Iterator.next()` không?

Không. Mảng được ngôn ngữ xử lý theo tham chiếu mảng, độ dài và chỉ số.

**Câu 2.** Hàm ở biểu thức nguồn có được gọi lại cho mỗi phần tử không?

Không. Biểu thức nguồn được đánh giá một lần cho lần bắt đầu vòng lặp đó.

**Câu 3.** Vì sao gán biến nguồn sang mảng khác không đổi những phần tử vòng lặp đang duyệt?

Vì vòng lặp đã giữ tham chiếu mảng ban đầu. Gán lại biến bên ngoài không thay tham chiếu đã giữ.

**Câu 4.** Khi duyệt hết hai phần tử `Iterable` bình thường, phần điều khiển gọi `hasNext()` và `next()` bao nhiêu lần?

`hasNext()` ba lần và `next()` hai lần. Số này không tính các lời gọi mà iterator có thể tự thực hiện nội bộ.

**Câu 5.** Vì sao `Arrays.asList(new int[]{7, 8})` có kích thước `1`?

Vì phần tử của list là một đối tượng mảng `int[]`. Lời gọi không chuyển từng `int` thành một phần tử `Integer` trong list.
