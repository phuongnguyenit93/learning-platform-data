# Kiểu của biến vòng lặp và chuyển đổi kiểu phần tử

## 1. Biến `for-each` nhận một giá trị mới ở mỗi lượt

Cú pháp cơ bản:

```java
for (ElementType element : source) {
    System.out.println(element);
}
```

Ở mỗi lượt, một phần tử tiếp theo của mảng hoặc đối tượng `Iterable` được dùng để khởi tạo biến cục bộ `element`.

Cần xác định hai điều riêng:

1. Kiểu phần tử mà biểu thức `source` cung cấp theo khai báo tĩnh.
2. Kiểu của biến vòng lặp và các chuyển đổi được phép từ phần tử sang biến đó.

Ví dụ:

```java
List<String> names = List.of("Lan", "Minh");
for (CharSequence name : names) {
    System.out.println(name.length());
}
```

Nguồn cung cấp `String`, còn biến vòng lặp có kiểu `CharSequence`. Đây là mở rộng kiểu tham chiếu hợp lệ vì `String` thực hiện `CharSequence`.

Vòng lặp không tự nhìn từng đối tượng để chọn lại kiểu khai báo cho biến. Kiểu của biến đã được xác định khi biên dịch; ở lượt khác nhau, giá trị có thể khác nhưng các thao tác được phép vẫn dựa trên kiểu đó.

Quy tắc chính thức nằm trong [JLS §14.14.2 về enhanced for](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.14.2). Bài dùng các ví dụ còn áp dụng trong Java hiện đại, chạy được từ Java 17.

## 2. Giữ nguyên kiểu hoặc mở rộng kiểu tham chiếu

Với một `List<String>`, các kiểu biến sau đều phù hợp:

```java
for (String value : names) {
    System.out.println(value.toUpperCase());
}

for (CharSequence value : names) {
    System.out.println(value.length());
}

for (Object value : names) {
    System.out.println(value);
}
```

Lựa chọn kiểu ảnh hưởng những phương thức có thể gọi trong thân vòng lặp. Qua biến `Object`, không gọi trực tiếp được `length()` của chuỗi, dù đối tượng hiện tại thực tế là `String`.

Ngược lại, không tự thu hẹp từ kiểu nguồn rộng xuống kiểu con:

```java
List<Number> numbers = List.of(1, 2);
// for (Integer value : numbers) { } // Lỗi biên dịch.
```

Khai báo `List<Number>` cho phép có nhiều loại `Number`, như `Double`. Việc dữ liệu mẫu hiện đang có hai số nguyên không đổi hợp đồng tĩnh của nguồn.

Nếu cần xử lý một kiểu con có điều kiện, hãy đọc bằng kiểu được bảo đảm rồi kiểm tra:

```java
for (Number value : numbers) {
    if (value instanceof Integer integer) {
        System.out.println(integer);
    }
}
```

Đây là lựa chọn xử lý từng giá trị rõ ràng trong thân vòng lặp, khác với việc yêu cầu biến vòng lặp tự thu hẹp kiểu một cách không an toàn.

## 3. Kiểu nguyên thủy có thể được mở rộng

Với mảng `int[]`:

```java
int[] counts = {1, 2, 3};

for (long count : counts) {
    System.out.println(count);
}
```

Mỗi giá trị `int` được mở rộng sang `long` trước khi thân vòng lặp sử dụng biến `count`.

Các chuyển đổi mở rộng nguyên thủy phù hợp khác cũng có thể dùng, chẳng hạn `int → double`. Tuy nhiên, mở rộng kiểu không luôn đồng nghĩa giữ được mọi chữ số chính xác: chuyển một `int` đủ lớn sang `float` có thể làm tròn.

Không có thu hẹp nguyên thủy ngầm định chỉ vì các phần tử mẫu đang nhỏ:

```java
int[] counts = {1, 2};
// for (byte count : counts) { } // Lỗi biên dịch.
```

Các phần tử của mảng không trở thành những hằng số có thể tự thu hẹp chỉ vì mảng được khởi tạo bằng các literal nhỏ. Nếu nghiệp vụ thật sự yêu cầu `byte`, cần quyết định cách kiểm tra miền giá trị và chuyển đổi một cách tường minh trong thân vòng lặp.

```java
for (int count : counts) {
    if (count < Byte.MIN_VALUE || count > Byte.MAX_VALUE) {
        throw new IllegalArgumentException("Value is outside byte range");
    }
    byte small = (byte) count;
    System.out.println(small);
}
```

Không tự thêm cast mà bỏ qua hệ quả mất dữ liệu; kiểm tra miền là một phần của quyết định chuyển đổi.

## 4. Boxing và unboxing ở biến vòng lặp

### Từ nguyên thủy sang wrapper

```java
int[] counts = {1, 2};
for (Integer count : counts) {
    System.out.println(count);
}
```

Mỗi giá trị `int` được boxing sang `Integer`. Cũng có thể dùng `Number` hoặc `Object` khi chuỗi chuyển đổi boxing rồi mở rộng tham chiếu phù hợp.

Không được giả định boxing luôn cấp phát một đối tượng wrapper mới; cách tái sử dụng wrapper không phải ý nghĩa của kiểu biến vòng lặp.

### Từ wrapper sang nguyên thủy

```java
List<Integer> counts = List.of(1, 2);
for (int count : counts) {
    System.out.println(count);
}
```

Mỗi `Integer` được unboxing để lấy `int`.

Có thể kết hợp unboxing rồi mở rộng nguyên thủy:

```java
for (long count : counts) {
    System.out.println(count);
}
```

Luồng giá trị là `Integer → int → long`.

### Không phải mọi chuỗi chuyển đổi số đều được tự động ghép

```java
int[] counts = {1, 2};
// for (Long count : counts) { } // Lỗi: không tự ghép int → long → Long.

List<Long> totals = List.of(1L, 2L);
// for (int total : totals) { } // Lỗi: long → int là thu hẹp.
```

Đừng hiểu `for-each` như một bộ chuyển đổi số tùy ý. Các quy tắc boxing, unboxing và chuyển đổi nguyên thủy vẫn có giới hạn.

Tương tự, một biến kiểu `Number` không tự có phép unboxing trực tiếp thành `int`:

```java
List<Number> mixed = List.of(1, 2.5);
// for (int value : mixed) { } // Lỗi biên dịch.

for (Number value : mixed) {
    int converted = value.intValue();
    System.out.println(converted);
}
```

Ở đoạn hợp lệ, `intValue()` là một lời gọi chuyển đổi do người viết chọn; nó có thể bỏ phần thập phân hoặc mất thông tin theo kiểu số cụ thể. Nó không có cùng ý nghĩa với việc chứng minh mọi phần tử vốn là `Integer`.

Các phép chuyển đổi liên quan được đặc tả trong [JLS Chương 5](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html).

## 5. Wildcard giới hạn kiểu có thể dùng để đọc

Xét các nguồn:

```java
List<? extends Number> upper = List.of(1, 2);
List<?> unknown = List.of("A", "B");
List<? super Integer> lower = new ArrayList<Number>();
```

Các lựa chọn thực tế:

| Kiểu tĩnh của nguồn | Kiểu biến đọc được bảo đảm |
| --- | --- |
| `List<Integer>` | `Integer`, `Number`, `Object`; hoặc kiểu nguyên thủy qua unboxing phù hợp |
| `List<? extends Number>` | `Number` hoặc `Object` |
| `List<?>` | `Object` |
| `List<? super Integer>` | `Object` |

`? super Integer` giúp ghi `Integer` vào nguồn khi đối tượng hỗ trợ, nhưng không bảo đảm đọc ra `Integer`. Một `List<Object>` phù hợp với kiểu này có thể chứa cả chuỗi.

```java
for (Number value : upper) {
    System.out.println(value.doubleValue());
}

for (Object value : unknown) {
    System.out.println(value);
}

// for (Integer value : upper) { } // Không biết upper chứa kiểu Number cụ thể nào.
// for (String value : unknown) { } // Không biết phần tử là String.
// for (Integer value : lower) { }  // Cận dưới không phải bảo đảm đọc Integer.
```

Nguồn `upper` ở ví dụ có dữ liệu số nguyên không làm biến vòng lặp được phép tự chọn `Integer`. Phần quyết định là kiểu tĩnh của biểu thức đang được duyệt.

## 6. `var` suy luận từ kiểu phần tử được cung cấp

Có thể dùng `var` ở đầu vòng lặp:

```java
for (var value : List.of(1, 2)) {
    System.out.println(value);
}
```

Trong các trường hợp thông dụng:

| Nguồn | Kiểu biến `var` |
| --- | --- |
| `int[]` | `int` |
| `Integer[]` | `Integer` |
| `List<Integer>` | `Integer` |
| `List<? extends Number>` | `Number` |
| `List<?>` | `Object` |
| `List<? super Integer>` | `Object` |

`var` không có nghĩa biến thay đổi kiểu theo từng phần tử. Trình biên dịch vẫn chọn một kiểu tĩnh; với các biến kiểu capture, quy tắc suy luận giữ kiểu phù hợp có thể dùng trong thân vòng lặp.

Hai trường hợp dễ nhầm:

```java
for (var value : new int[]{1}) {
    // value là int, không phải Integer.
    System.out.println(value + 1);
}

for (var value : List.of(1)) {
    // value là Integer; phép cộng phía dưới sẽ unboxing khi cần.
    System.out.println(value + 1);
}
```

Kết quả số giống nhau không có nghĩa hai biến mang cùng kiểu. Nếu cần hiểu một lời gọi overload hoặc lý do có unboxing, phải biết nguồn tĩnh của `var`.

Trong chương trình đầy đủ, các overload `kind(...)` giúp quan sát kiểu tĩnh mà trình biên dịch lựa chọn, không chỉ nhìn lớp thực tế của một đối tượng.

## 7. Lỗi khi chạy có thể xảy ra trước khi vào thân vòng lặp

### Phần tử wrapper là `null`

```java
List<Integer> values = Arrays.asList(1, null, 3);
for (int value : values) {
    System.out.println(value);
}
```

Lượt đầu in `1`. Khi lấy phần tử thứ hai, unboxing `null` thành `int` gây `NullPointerException` trước khi thân vòng lặp được thực hiện cho phần tử đó.

Đổi biến thành `Integer` tránh unboxing ngay tại bước nhận phần tử:

```java
for (Integer value : values) {
    if (value == null) {
        continue;
    }
    System.out.println(value);
}
```

Đây là cách chủ động xử lý theo hợp đồng. Không nên thay `null` bằng `0` một cách tùy ý nếu nghiệp vụ phân biệt “không có giá trị” với “giá trị bằng không”.

### Bản thân nguồn là `null`

Một mảng hoặc `Iterable` có giá trị `null` làm vòng lặp thất bại khi bắt đầu truy cập nguồn. Điều đó khác với collection rỗng: nguồn rỗng hợp lệ chỉ khiến thân vòng lặp không chạy lần nào.

### Dữ liệu generic đã bị làm sai kiểu

Khi duyệt `Iterable` generic, mã được sinh có thể có cast để dùng kết quả `Iterator.next()` như kiểu nguồn yêu cầu. Nếu hợp đồng kiểu đã bị phá vỡ ở nơi khác, lỗi `ClassCastException` có thể xuất hiện khi nhận phần tử, dù dòng `for-each` không viết cast tường minh.

Không dùng cast unchecked để “sửa” kiểu biến vòng lặp. Hãy sửa nguồn làm mất an toàn kiểu hoặc xác thực dữ liệu trước khi sử dụng theo kiểu cụ thể.

Quy tắc unboxing, bao gồm trường hợp `null`, có trong [JLS §5.1.8](https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.8).

## 8. Biến vòng lặp không phải một bí danh của ô chứa phần tử

Với mảng nguyên thủy:

```java
int[] values = {1, 2};
for (int value : values) {
    value = 99;
}
```

Mảng vẫn chứa `1` và `2`. Phép gán chỉ thay giá trị của biến cục bộ trong lượt hiện tại, không ghi vào ô mảng tương ứng.

Với phần tử tham chiếu, biến nhận một bản sao của tham chiếu. Vì vậy phải phân biệt:

- Gán biến sang một đối tượng khác: không tự thay phần tử trong nguồn.
- Gọi phương thức sửa trạng thái trên đối tượng mà tham chiếu đang trỏ tới: có thể làm đối tượng được chia sẻ thay đổi.

Ví dụ:

```java
List<StringBuilder> values = List.of(new StringBuilder("A"));
for (StringBuilder value : values) {
    value.append("B");
}
System.out.println(values); // [AB]
```

Danh sách không cho thay cấu trúc không có nghĩa các đối tượng phần tử đều bất biến. Đây là hệ quả của việc nhận tham chiếu, không phải `for-each` cung cấp quyền thay thế phần tử trong collection.

## 9. Chương trình hoàn chỉnh

Lưu vào `ForEachVariableTypesDemo.java`, dùng Java 17 trở lên:

```java
import java.util.Arrays;
import java.util.List;

public class ForEachVariableTypesDemo {
    static String kind(int value) { return "int"; }
    static String kind(Integer value) { return "Integer"; }
    static String kind(Number value) { return "Number"; }
    static String kind(Object value) { return "Object"; }

    public static void main(String[] args) {
        int[] primitiveValues = {1, 2};
        long arraySum = 0;
        for (long value : primitiveValues) {
            arraySum += value;
        }
        int boxedSum = 0;
        for (Integer value : primitiveValues) {
            boxedSum += value;
        }
        System.out.println("array widening sum = " + arraySum);
        System.out.println("array boxing sum = " + boxedSum);

        List<Integer> wrappers = List.of(3, 4);
        long listSum = 0;
        for (long value : wrappers) {
            listSum += value;
        }
        System.out.println("unbox then widen sum = " + listSum);

        String[] names = {"Lan", "Minh"};
        int lengthSum = 0;
        for (CharSequence name : names) {
            lengthSum += name.length();
        }
        System.out.println("reference widening lengths = " + lengthSum);

        for (var value : new int[]{5}) {
            System.out.println("var from int[] = " + kind(value));
        }
        for (var value : List.of(5)) {
            System.out.println("var from List<Integer> = " + kind(value));
        }
        List<? extends Number> upperBounded = List.of(5);
        for (var value : upperBounded) {
            System.out.println("var from extends Number = " + kind(value));
        }
        List<?> unknown = List.of(5);
        for (var value : unknown) {
            System.out.println("var from List<?> = " + kind(value));
        }

        int enteredBodies = 0;
        try {
            for (int value : Arrays.asList(1, null, 3)) {
                enteredBodies++;
            }
        } catch (NullPointerException ex) {
            System.out.println("unboxing NPE after body count = " + enteredBodies);
        }

        for (int value : primitiveValues) {
            value = 99;
        }
        System.out.println("array after local assignment = " + Arrays.toString(primitiveValues));

        List<StringBuilder> builders = List.of(new StringBuilder("A"));
        for (StringBuilder builder : builders) {
            builder.append("B");
        }
        System.out.println("shared object = " + builders);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror -encoding UTF-8 ForEachVariableTypesDemo.java
java ForEachVariableTypesDemo
```

Kết quả chuẩn:

```text
array widening sum = 3
array boxing sum = 3
unbox then widen sum = 7
reference widening lengths = 7
var from int[] = int
var from List<Integer> = Integer
var from extends Number = Number
var from List<?> = Object
unboxing NPE after body count = 1
array after local assignment = [1, 2]
shared object = [AB]
```

Các overload `kind` được lựa chọn khi biên dịch theo kiểu biểu thức `value`. Chúng cho thấy kiểu suy luận của biến; không phải một thuật toán dùng `getClass()` để đoán lại kiểu generic lúc chạy.

Dòng đếm thân vòng lặp cho thấy phần tử `null` gây lỗi ở bước unboxing: chỉ thân vòng lặp của phần tử đầu đã được thực hiện. Hai dòng cuối phân biệt việc gán lại biến cục bộ với việc sửa đối tượng được chia sẻ.

## 10. Cách chọn kiểu biến phù hợp

1. Đọc kiểu tĩnh của mảng hoặc `Iterable` nguồn trước khi viết thân vòng lặp.
2. Dùng kiểu phần tử cụ thể khi cần các thao tác của kiểu đó và nguồn bảo đảm được.
3. Dùng kiểu cha khi chỉ cần giao diện chung; đừng thu hẹp vì dữ liệu mẫu tình cờ cùng một lớp.
4. Với số, xác định rõ có boxing, unboxing, mở rộng hoặc chuyển đổi tường minh nào xảy ra.
5. Nếu nguồn có thể chứa `null`, chọn biến wrapper/tham chiếu và xử lý theo hợp đồng trước khi unboxing.
6. Dùng `var` khi kiểu từ nguồn đủ rõ với người đọc; nhớ rằng wildcard có thể khiến kiểu suy luận rộng hơn những đối tượng đang quan sát.

## 11. Tự kiểm tra

**Câu 1.** Với `List<Integer> values`, `for (long value : values)` có hợp lệ không?

Có. `Integer` được unboxing thành `int`, rồi mở rộng thành `long`.

**Câu 2.** Với `int[] values`, vì sao `for (Long value : values)` không tương đương trường hợp trên?

Nó đòi chuỗi `int → long → Long`, không phải chuỗi unboxing rồi mở rộng. Java không tự ghép chuỗi chuyển đổi đó để khởi tạo biến vòng lặp.

**Câu 3.** `var` khi duyệt `List<?>` có tự chọn `String` nếu mọi phần tử hiện tại đều là chuỗi không?

Không. Trong trường hợp này biến có kiểu `Object`, theo thông tin tĩnh nguồn cung cấp.

**Câu 4.** Gán `value = 99` trong vòng lặp qua `int[]` có đổi phần tử mảng không?

Không. Nó chỉ gán biến cục bộ. Muốn ghi lại ô mảng, cần thao tác với vị trí nguồn phù hợp.

**Câu 5.** Một `Integer` bằng `null` gây lỗi ở đâu khi biến vòng lặp là `int`?

Ở bước unboxing khi khởi tạo biến của lượt đó, trước khi thân vòng lặp xử lý phần tử tương ứng.
