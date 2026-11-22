# Wildcard lồng nhau và giới hạn của phép bắt giữ trong Java Generics

Khi gặp những kiểu như `List<List<?>>`, `List<? extends List<?>>` hoặc `List<? extends List<? extends Number>>`, chỉ một dấu `?` cũng đã cần chú ý đến hướng đọc/ghi; **nhiều dấu `?` ở những tầng khác nhau không hề có nghĩa chúng cùng một kiểu**. Java kiểm tra ràng buộc ở từng tầng generic và có cơ chế *wildcard capture* để tạm đặt tên cho một kiểu ẩn. Nhưng capture có giới hạn: nó không biến các wildcard độc lập thành một kiểu chung, không cho phép ghi giá trị tùy ý, và không thay đổi tính bất biến của generic.

Bài này làm rõ ba câu hỏi:

1. **Wildcard nằm ở tầng nào?** Tầng danh sách ngoài và tầng danh sách trong quyết định những phép gán và cập nhật được phép.
2. **Capture giải quyết được gì?** Một phương thức generic có thể nắm bắt một kiểu ẩn để đọc và ghi lại **giá trị cùng kiểu của chính collection đó**.
3. **Capture không giải quyết được gì?** Nó không chứng minh hai wildcard độc lập là cùng kiểu, không ép danh sách của subtype thành danh sách của supertype, và không vượt qua giới hạn sửa dữ liệu của đối tượng thật.

Các ví dụ runnable sử dụng Java 17 trở lên. Các đoạn cố ý sai kiểu đều được chú thích và giải thích riêng, không phải các chương trình chạy độc lập.

## 1. Từ một wildcard đến nhiều tầng generic

`List<?>` có một element type chưa biết: đọc ra an toàn như `Object`, nhưng không được tùy ý `add("text")`. Nó **không** tương đương `List<Object>`. Java có thể capture dấu `?` thành một kiểu tạm có tên nội bộ `CAP#1`; generic helper `<E>` giúp giữ cùng element type khi đọc rồi ghi lại vào **chính list đó**.

Khi có **danh sách các danh sách**, vấn đề không còn nằm ở một dấu `?` đơn lẻ: vị trí wildcard ở **tầng ngoài** khác wildcard nằm trong **kiểu phần tử của tầng trong**. Hai hàng khác nhau có thể chứa các loại dữ liệu khác nhau, dù đều được nhìn dưới `List<?>`.

Ví dụ minh họa (đặt trong method có import `java.util.List`):

~~~java
List<List<?>> rows = List.of(List.of("A"), List.of(1));
Object first = rows.get(0).get(0); // "A"
Object next  = rows.get(1).get(0); // 1
~~~

Mã chỉ đọc nên không cần capture helper. Nếu cần thay đổi một hàng cụ thể, phải xác định **capture đang thuộc tầng nào và danh sách thực có mutable không**. Các phần sau phân biệt `List<List<?>>`, `List<? extends List<?>>` và cách đặt helper ở đúng tầng; không được suy từ cùng ký hiệu `?` rằng hai hàng có một element type chung.

## 2. Phân biệt các tầng kiểu: ba khai báo trông gần giống nhưng rất khác

Xét ba kiểu:

~~~java
List<?> a;
List<List<?>> b;
List<? extends List<?>> c;
~~~

Chúng khác nhau ở **vị trí wildcard**:

| Kiểu | Wildcard ở đâu? | Đọc từ danh sách ngoài | Thêm hàng mới vào danh sách ngoài |
| --- | --- | --- | --- |
| `List<?>` | Ngay phần tử của danh sách ngoài | `Object` | Không thêm hàng không phải `null` |
| `List<List<?>>` | Trong kiểu phần tử; tầng ngoài có đối số kiểu chính xác `List<?>` | `List<?>` | Có thể thêm một `List<X>` bất kỳ vì nó dùng được như `List<?>` |
| `List<? extends List<?>>` | Tầng ngoài có wildcard với upper bound `List<?>` | `List<?>` | Không thêm hàng không phải `null` vì không biết kiểu phần tử thực của tầng ngoài |

### 2.1. `List<List<?>>`: danh sách ngoài biết phần tử là `List<?>`

~~~java
List<List<?>> rows = new ArrayList<>();
rows.add(new ArrayList<String>(List.of("A", "B")));
rows.add(new ArrayList<Integer>(List.of(1, 2)));

List<?> firstRow = rows.get(0); // Hợp lệ.
// firstRow.add("C");           // LỖI: không biết kiểu của hàng này.
rows.add(List.of(true, false)); // Hợp lệ: thêm một hàng Boolean.
~~~

Đây là đoạn minh họa cần import `java.util.*` và đặt trong class. `rows.add(...)` biên dịch vì **kiểu phần tử của danh sách ngoài chính xác là `List<?>`**, và `List<String>`, `List<Integer>`, `List<Boolean>` đều chuyển được sang góc nhìn `List<?>`.

Tuy nhiên, khi lấy ra một hàng, biến `List<?>` lại không biết **kiểu phần tử bên trong hàng ấy**. Việc danh sách ngoài chứa được nhiều kiểu hàng không cho phép trộn các kiểu phần tử trong một hàng cụ thể.

### 2.2. `List<? extends List<?>>`: tầng ngoài cũng có kiểu ẩn

~~~java
List<List<Integer>> integerRows = new ArrayList<>();
integerRows.add(new ArrayList<>(List.of(1, 2)));

List<? extends List<?>> rows = integerRows;
List<?> firstRow = rows.get(0); // Hợp lệ.

// rows.add(List.of("X")); // LỖI: tầng ngoài có wildcard.
// rows.add(List.of(3));   // CŨNG LỖI.
~~~

Đây là đoạn minh họa cần import `java.util.*` và đặt trong class. `integerRows` có đối số kiểu `List<Integer>`; đối số này phù hợp upper bound `List<?>` nên có thể gán sang `List<? extends List<?>>`.

Tuy nhiên, compiler **không biết chính xác loại hàng mà danh sách ngoài chấp nhận**, chỉ biết nó là một subtype của `List<?>`. Đích thật đang nhận các hàng `List<Integer>`; cho thêm một `List<String>` là nguy hiểm. Vì vậy, ngay cả `List<Integer>` mới cũng không được thêm qua tham chiếu `rows`, bởi kiểu tĩnh không giữ được thông tin rằng đối số kiểu thực đúng là `List<Integer>`.

### 2.3. Sự khác nhau có thể quan sát được bằng một phép gán

~~~java
List<List<Integer>> integerRows = new ArrayList<>();

List<? extends List<?>> accepted = integerRows; // Hợp lệ.
// List<List<?>> rejected = integerRows;         // LỖI BIÊN DỊCH.
~~~

**Vì sao dòng thứ hai sai?** Java generic bất biến theo đối số kiểu tầng ngoài. Nếu nó cho phép chuyển `List<List<Integer>>` sang `List<List<?>>`, ta có thể gọi `rejected.add(List.of("text"))`, khiến danh sách được khai báo chứa các hàng `List<Integer>` bỗng có một hàng `List<String>`.

**Vì sao dòng đầu đúng?** `? extends List<?>` giữ ràng buộc rằng kiểu hàng thật có thể là bất kỳ subtype cụ thể nào của `List<?>`; do không cho thêm hàng tùy ý, phép gán vẫn an toàn.

Đây là nguyên tắc quan trọng nhất của wildcard lồng nhau: **chỗ đặt `?` quan trọng không kém phần upper bound đứng sau nó**.

## 3. Hai tầng wildcard có thể cùng xuất hiện

Bây giờ xét:

~~~java
List<? extends List<? extends Number>> groups;
~~~

Hãy đọc **từ trong ra ngoài**:

1. `List<? extends Number>` là một danh sách mà mỗi phần tử đọc ra dùng được như `Number`. Nó có thể thực sự là `List<Integer>`, `List<Double>` hoặc `List<Number>`.
2. `List<? extends List<? extends Number>>` là một danh sách ngoài có kiểu hàng thực là một subtype cụ thể của `List<? extends Number>`. Đọc một hàng ra sẽ sử dụng được như `List<? extends Number>`.
3. Qua tham chiếu này, ta không tự ý thêm một hàng mới vào danh sách ngoài, và cũng không tự ý thêm một `Number` mới vào hàng lấy ra. Nhưng ta có thể **đọc mỗi phần tử số như `Number`**.

Ví dụ:

~~~java
List<List<Integer>> integerGroups =
        List.of(List.of(1, 2), List.of(3));

List<? extends List<? extends Number>> groups = integerGroups;

List<? extends Number> firstGroup = groups.get(0);
Number firstNumber = firstGroup.get(0); // Hợp lệ.

// groups.add(List.of(4, 5));  // LỖI ở tầng ngoài.
// firstGroup.add(3.14);       // LỖI ở tầng trong.
~~~

Đây là đoạn minh họa cần import `java.util.List` và đặt trong class. Tương tự, kiểu `List<List<Double>>` có thể gán vào biến `groups`.

Quan sát kỹ rằng **mỗi tầng wildcard có một ràng buộc khác**. Tầng ngoài kiểm soát kiểu hàng; tầng trong kiểm soát kiểu phần tử của một hàng. Một phép capture ở tầng trong **không tự động mở khóa** quyền thêm hàng vào tầng ngoài.

## 4. Chương trình Java 17+: quan sát các tầng và thao tác an toàn

Tạo tệp **`NestedWildcardViewsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class NestedWildcardViewsDemo {
    private static void showRows(List<? extends List<?>> rows) {
        for (List<?> row : rows) {
            System.out.println("row = " + row);
            for (Object item : row) {
                System.out.println("  item = " + item);
            }
        }
    }

    public static void main(String[] args) {
        List<List<Integer>> integerRows = new ArrayList<>();
        integerRows.add(new ArrayList<>(List.of(1, 2)));
        integerRows.add(new ArrayList<>(List.of(3)));

        List<List<?>> mixedRows = new ArrayList<>();
        mixedRows.add(new ArrayList<>(List.of("A", "B")));
        mixedRows.add(new ArrayList<>(List.of(true, false)));

        showRows(integerRows);
        showRows(mixedRows);
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac NestedWildcardViewsDemo.java
java NestedWildcardViewsDemo
~~~

Stdout chính xác:

~~~text
row = [1, 2]
  item = 1
  item = 2
row = [3]
  item = 3
row = [A, B]
  item = A
  item = B
row = [true, false]
  item = true
  item = false
~~~

Phương thức `showRows` nhận cả hai kiểu nguồn vì `List<List<Integer>>` và `List<List<?>>` đều phù hợp `List<? extends List<?>>`. Ở mỗi lần lặp, một hàng được đọc như `List<?>` và từng phần tử như `Object`. Không có cast unchecked hoặc phép gán thiếu an toàn.

Đừng suy từ `mixedRows` có thể chứa nhiều loại hàng rằng **mọi hàng đều nhận được mọi loại phần tử**. Hàng đầu thật là một `ArrayList<String>` nên vẫn có hợp đồng phần tử riêng của nó.

## 5. Capture một hàng bên trong danh sách lồng nhau

Nếu cần thay đổi vị trí của các phần tử *trong chính một hàng*, có thể dùng helper generic để nắm bắt kiểu của hàng ấy.

Tạo **`NestedCaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class NestedCaptureDemo {
    public static void swapEndsInEveryRow(List<? extends List<?>> rows) {
        for (List<?> row : rows) {
            swapCaptured(row);
        }
    }

    private static <E> void swapCaptured(List<E> row) {
        int last = row.size() - 1;
        if (last > 0) {
            E first = row.get(0);
            row.set(0, row.get(last));
            row.set(last, first);
        }
    }

    public static void main(String[] args) {
        List<List<?>> mixed = new ArrayList<>();
        mixed.add(new ArrayList<>(List.of("A", "B", "C")));
        mixed.add(new ArrayList<>(List.of(1, 2)));
        mixed.add(new ArrayList<>(List.of(true)));

        swapEndsInEveryRow(mixed);
        System.out.println(mixed);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac NestedCaptureDemo.java
java NestedCaptureDemo
~~~

Stdout:

~~~text
[[C, B, A], [2, 1], [true]]
~~~

Diễn giải chính xác:

1. `swapEndsInEveryRow` nhận một danh sách có các hàng mà kiểu thực chưa biết, nhưng mỗi hàng sử dụng được như `List<?>`.
2. Mỗi lần lặp tạo một tham chiếu `row: List<?>` tới **một hàng cụ thể**.
3. Lời gọi `swapCaptured(row)` cho compiler capture đối số kiểu ẩn của **hàng hiện tại** thành `E`.
4. Trong `swapCaptured`, `get` và `set` cùng sử dụng `E` nên hoán đổi các phần tử **của chính hàng đó** an toàn về kiểu.
5. Khi vòng lặp chuyển sang một hàng khác, một capture khác có thể đại diện cho một kiểu phần tử hoàn toàn khác. Helper không ép mọi hàng thành cùng một `E`.

Phương thức không cần `@SuppressWarnings("unchecked")` và không dùng raw type. Việc `mixed` là `ArrayList` gồm các hàng `ArrayList` giúp `set` hoạt động lúc chạy; nếu một hàng được tạo bởi `List.of(...)`, `set` sẽ ném `UnsupportedOperationException` dù capture thành công.

### Tại sao đây không phải cách “đưa bất kỳ Object nào vào hàng”?

Giả sử helper:

~~~java
private static <E> void addCaptured(List<E> row, E value) {
    row.add(value);
}
~~~

Đây là **phương thức minh họa cần đặt trong class với `import java.util.List;`**. Việc có tham số `E` không tự tạo ra một giá trị `E` mới. Nếu caller chỉ có `List<?>` và một `Object` bất kỳ thì vẫn không thể chứng minh `Object` phù hợp với `E` ẩn:

~~~java
static void addUnknown(List<?> row, Object value) {
    // addCaptured(row, value); // LỖI: không bảo đảm value có kiểu E ẩn.
}
~~~

Vì vậy, **helper generic chỉ giúp diễn đạt quan hệ kiểu thật sự được bảo đảm**, chẳng hạn giá trị lấy ra từ chính `List<E>`. Nó không phải công cụ bỏ qua kiểm tra kiểu.

## 6. Capture tầng ngoài khác với capture tầng trong

Có hai công việc hoàn toàn khác nhau:

- **Hoán đổi hai hàng có sẵn trong cùng danh sách ngoài:** cần giữ đúng kiểu hàng ẩn của tầng ngoài.
- **Hoán đổi hai phần tử có sẵn trong cùng một hàng:** cần giữ đúng kiểu phần tử ẩn của tầng trong.

Tầng nào bị wildcard che đi, tầng ấy có thể cần capture riêng. Chương trình sau minh họa **capture tầng ngoài** bằng việc hoán đổi hai hàng `List<Integer>` trong một `List<List<Integer>>` được nhận dưới góc nhìn rộng hơn.

Tạo **`OuterCaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class OuterCaptureDemo {
    static void swapOuterRows(List<? extends List<?>> rows) {
        if (rows.size() >= 2) {
            swapCaptured(rows, 0, 1);
        }
    }

    private static <E> void swapCaptured(List<E> list, int i, int j) {
        E first = list.get(i);
        list.set(i, list.get(j));
        list.set(j, first);
    }

    public static void main(String[] args) {
        List<List<Integer>> rows = new ArrayList<>();
        rows.add(new ArrayList<>(List.of(1, 2)));
        rows.add(new ArrayList<>(List.of(3, 4)));

        swapOuterRows(rows);

        System.out.println(rows);
    }
}
~~~

~~~bash
javac OuterCaptureDemo.java
java OuterCaptureDemo
~~~

Stdout chính xác:

~~~text
[[3, 4], [1, 2]]
~~~

Ở helper, `E` là kiểu hàng thực của **danh sách ngoài** (ở ví dụ là `List<Integer>`), chứ không phải kiểu phần tử `Integer` bên trong mỗi hàng. Hoán đổi hai hàng vốn cùng một danh sách là an toàn vì cả hai có cùng kiểu phần tử của collection ngoài.

Không nên đọc chương trình này thành “wildcard capture cho phép thêm một hàng `List<String>` mới”. Capture chỉ giữ kiểu `E` của những hàng **đang có**, không cho phép tạo một giá trị bất kỳ thuộc subtype của `List<?>` rồi chèn vào.

## 7. Giới hạn quan trọng: hai wildcard độc lập không đồng nhất với nhau

Một nhầm lẫn phổ biến là nếu hai tham số cùng viết `List<?>` thì chúng “cùng một wildcard”. Thực tế mỗi vị trí wildcard chỉ biết có một kiểu ẩn; **không có điều kiện nào khẳng định hai kiểu ẩn bằng nhau**.

~~~java
List<?> first = new ArrayList<String>(List.of("A"));
List<?> second = new ArrayList<Integer>(List.of(1));

// first.set(0, second.get(0)); // LỖI BIÊN DỊCH.
~~~

Đây là đoạn minh họa cần import `java.util.*` và đặt trong class. Nếu phép gán được chấp nhận, `Integer` sẽ bị ghi vào danh sách chứa `String`. Cả hai biến cùng viết `List<?>` hoàn toàn không đủ để bảo đảm an toàn.

Tương tự trong một danh sách lồng nhau:

~~~java
List<List<?>> rows = new ArrayList<>();
rows.add(new ArrayList<String>(List.of("A")));
rows.add(new ArrayList<Integer>(List.of(1)));

List<?> row0 = rows.get(0);
List<?> row1 = rows.get(1);

// row0.set(0, row1.get(0)); // LỖI BIÊN DỊCH.
~~~

Một helper generic nắm bắt `row0` cũng không chứng minh phần tử từ `row1` có cùng kiểu. Việc hai hàng cùng thuộc một `List<List<?>>` chỉ bảo đảm **mỗi hàng là một `List<?>`**, không bảo đảm **các hàng có cùng đối số kiểu**.

### Giải pháp khi thực sự cần liên hệ kiểu giữa nguồn và đích

Nếu bài toán yêu cầu chuyển một phần tử từ danh sách nguồn sang danh sách đích có khả năng nhận kiểu đó, hãy **diễn đạt quan hệ bằng type parameter và cận rõ ràng**:

~~~java
static <T> void appendFirst(
        List<? extends T> source,
        List<? super T> destination) {
    if (!source.isEmpty()) {
        destination.add(source.get(0));
    }
}
~~~

Đây là **phương thức minh họa cần import `java.util.List` và đặt trong class**.

Với `List<Integer>` nguồn và `List<Number>` đích, compiler chứng minh được ràng buộc bằng PECS và lời gọi hợp lệ. Với `List<?>` nguồn và `List<?>` đích không có mối liên hệ khai báo, compiler không được tự giả định chúng cùng kiểu. **Nếu thông tin kiểu đã bị xóa khỏi API ở hai đầu**, có thể cần thiết kế lại API hoặc giữ generic type parameter xuyên suốt thay vì tìm cách “bắt giữ mạnh hơn”.

## 8. Giới hạn của wildcard lồng nhau khi truyền collection cấp hai

Xem các kiểu:

~~~java
List<List<Integer>> integerGroups = new ArrayList<>();
List<List<? extends Number>> groupSlots = new ArrayList<>();

// groupSlots = integerGroups; // LỖI BIÊN DỊCH.
groupSlots.add(new ArrayList<Integer>()); // Hợp lệ.
~~~

Đoạn minh họa cần import `java.util.*` và đặt trong class. Điểm dễ nhầm: `List<Integer>` **tương thích** với `List<? extends Number>`, nhưng không vì thế mà `List<List<Integer>>` trở thành subtype của `List<List<? extends Number>>`. Tầng ngoài vẫn **invariant** theo đối số kiểu.

Nếu phép gán vào `groupSlots` được cho phép, mã sau đó có thể thêm một `List<Double>` vào danh sách ban đầu chỉ chứa các `List<Integer>`. Compiler vì thế từ chối.

Cách để **nhận** một danh sách các nhóm subtype `Number` là:

~~~java
List<List<Integer>> integerGroups =
        List.of(List.of(1, 2), List.of(3));

List<? extends List<? extends Number>> readOnlyView = integerGroups;
~~~

“readOnlyView” là tên biến minh họa; nó không bảo đảm collection runtime bất biến. Nó là một **góc nhìn bị giới hạn việc thêm hàng/phần tử**. Hai dấu `? extends` cho phép đọc số an toàn qua cả hai tầng mà không mở quyền ghi sai kiểu.

### Một bảng phân biệt

| Kiểu tham số | Nhận `List<List<Integer>>`? | Có thể thêm một hàng `List<Double>` qua tham số? | Có thể đọc số như `Number`? |
| --- | --- | --- | --- |
| `List<List<Number>>` | Không | Không; chỉ thêm được một hàng có kiểu `List<Number>` | Có |
| `List<List<? extends Number>>` | Không | Có, vì `List<Double>` tương thích `List<? extends Number>` | Có |
| `List<? extends List<? extends Number>>` | Có | Không thêm hàng mới không phải `null` | Có |
| `List<? extends List<?>>` | Có | Không thêm hàng mới không phải `null` | Chỉ đọc phần tử như `Object` |

Ở hàng đầu, dù một `List<Number>` có thể chứa giá trị `Double`, bản thân `List<Double>` **không** phải là `List<Number>`. Bởi vậy không thể thêm nguyên hàng `List<Double>` vào `List<List<Number>>`. Hãy giữ riêng hai khái niệm *đối số kiểu của hàng* và *giá trị phần tử trong hàng*.

## 9. Ví dụ thực tế: làm phẳng nhiều nhóm số bằng nested producer

Một phương thức chỉ **đọc** các nhóm số nên nhận danh sách ngoài với hai tầng wildcard producer:

~~~java
static List<Number> flatten(
        List<? extends List<? extends Number>> groups) {
    List<Number> result = new ArrayList<>();
    for (List<? extends Number> group : groups) {
        for (Number number : group) {
            result.add(number);
        }
    }
    return result;
}
~~~

Đây là **phương thức minh họa cần import `java.util.*` và đặt trong class**. Nó chấp nhận danh sách gồm các hàng `Integer` hoặc `Double`; mọi phần tử đọc ra đều là `Number`. Danh sách kết quả là **một `ArrayList<Number>` mới**, nên việc thêm `Number` vào kết quả không hề vi phạm giới hạn ghi trên nguồn wildcard.

Tạo **`NestedFlattenDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class NestedFlattenDemo {
    static List<Number> flatten(
            List<? extends List<? extends Number>> groups) {
        List<Number> result = new ArrayList<>();
        for (List<? extends Number> group : groups) {
            for (Number value : group) {
                result.add(value);
            }
        }
        return result;
    }

    public static void main(String[] args) {
        List<List<Integer>> integerGroups =
                List.of(List.of(1, 2), List.of(3));
        List<List<Double>> doubleGroups =
                List.of(List.of(1.5, 2.5));

        System.out.println("integer groups = " + flatten(integerGroups));
        System.out.println("double groups = " + flatten(doubleGroups));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac NestedFlattenDemo.java
java NestedFlattenDemo
~~~

Stdout chính xác:

~~~text
integer groups = [1, 2, 3]
double groups = [1.5, 2.5]
~~~

Ở ví dụ này ta **không cần wildcard capture helper** vì chỉ đọc từ nguồn và thêm vào danh sách `result` có kiểu phần tử xác định `Number`. Không nên dùng capture chỉ vì thấy nhiều dấu `?`; hãy dùng khi thật sự cần liên kết giá trị đọc/ghi có cùng kiểu ẩn.

Nếu đầu vào cần chứa **nhiều loại hàng khác nhau trong cùng một danh sách ngoài**, có thể tạo `List<List<? extends Number>>` và thêm các hàng `List<Integer>`, `List<Double>` rồi gọi `flatten`. Điều này được phép vì mỗi hàng đều phù hợp `List<? extends Number>`; danh sách ngoài lúc ấy khai báo chính xác kiểu phần tử `List<? extends Number>`.

## 10. Khi cần cả nguồn lồng nhau và đích nhận phần tử

Kết hợp PECS với nested wildcard:

~~~java
static <T> void appendFlattened(
        List<? extends List<? extends T>> groups,
        List<? super T> destination) {
    for (List<? extends T> group : groups) {
        for (T value : group) {
            destination.add(value);
        }
    }
}
~~~

Đây là **phương thức minh họa**, cần import `java.util.List` và đặt trong class.

- `groups`: tầng ngoài đọc ra các nhóm, tầng trong đọc ra các `T` hoặc subtype của `T`.
- `destination`: nhận giá trị `T` hoặc subtype của `T`.
- `T` kết nối **hướng đọc từ các nhóm** với **hướng ghi vào đích**, không yêu cầu mọi nhóm phải chứa chính xác cùng subtype.
- Phương thức không đưa phần tử mới vào các nhóm nguồn nên không cần nắm bắt riêng kiểu của từng nhóm.

Ví dụ:

~~~java
List<List<Integer>> groups = List.of(List.of(1, 2), List.of(3));
List<Number> destination = new ArrayList<>();

appendFlattened(groups, destination);
System.out.println(destination); // [1, 2, 3]
~~~

Đây là đoạn lời gọi minh họa cần import `java.util.*` và đặt trong class cùng phương thức `appendFlattened`. Compiler có thể suy luận `T` phù hợp từ cả nguồn và đích, hoặc ta có thể gọi `ClassName.<Number>appendFlattened(groups, destination)` để chỉ định `T = Number` tường minh.

Ngược lại, nếu muốn ghi tất cả phần tử `Number` vào các hàng `List<Integer>`, phép ghi không an toàn: một `Double` có thể lọt vào hàng `Integer`. Không có cách đặt helper capture nào làm hợp đồng sai ấy trở thành đúng.

## 11. Capture không phải phép biến đổi runtime hoặc kỹ thuật “xóa” giới hạn

### 11.1. Capture không tạo ra đối tượng mới, không kiểm tra subtype thực

Khi gọi `helper(List<E>)` với tham số `List<?>`, compiler đưa ra một kiểu `E` tạm để kiểm tra biểu thức. Đây là **cơ chế compile-time**, không phải lời gọi tạo class đặc biệt ở runtime. Java generics sử dụng **type erasure**, nên chương trình không có thông tin đầy đủ về đối số generic của từng `List` tại runtime.

Không thể làm kiểm tra:

~~~java
Object value = List.of(1, 2);

// if (value instanceof List<String>) { ... } // LỖI BIÊN DỊCH.
if (value instanceof List<?> list) {
    System.out.println(list.size());
}
~~~

Đây là đoạn minh họa cần import `java.util.List` và đặt trong class. `instanceof List<?>` dùng được vì chỉ kiểm tra được đối tượng là `List`, không xác nhận subtype phần tử của nó.

### 11.2. Capture không chứng minh hai kiểu ẩn bằng nhau

Hai biến `List<?>` chứa hai danh sách cùng là `String` cũng **không trở thành một hợp đồng generic chung** chỉ vì dữ liệu hiện tại giống nhau. Compiler kiểm tra **chữ ký và ràng buộc kiểu**, không suy luận một đẳng thức generic mới từ việc nhìn nội dung runtime.

Nếu cần một API dùng hai danh sách có chung kiểu `E`, hãy giữ chữ ký `<E> ... (List<E> a, List<E> b)` từ lúc dữ liệu còn được định kiểu, hoặc cung cấp ràng buộc chuyển giá trị an toàn như `List<? extends E>` và `List<? super E>`.

### 11.3. Capture không bảo đảm collection có thể thay đổi

~~~java
List<?> immutable = List.of("A", "B");
swapCaptured(immutable); // Biên dịch, nhưng set ném UnsupportedOperationException.
~~~

Đoạn này là minh họa ở trong class có phương thức `swapCaptured(List<E>)` như đã định nghĩa ở trên. Khi helper sử dụng `set`, danh sách thật vẫn có quyền từ chối sửa. Điều tương tự áp dụng ở tầng ngoài và trong của một danh sách lồng nhau: mỗi tầng có thể được cài đặt bằng collection cho phép hoặc không cho phép sửa.

### 11.4. Capture không hợp thức hóa unchecked cast

~~~java
List<Integer> integers = new ArrayList<>();
@SuppressWarnings("unchecked")
List<String> forged = (List<String>) (List<?>) integers;
forged.add("wrong"); // Nguy cơ heap pollution.
~~~

Đây là **mã minh họa nguy cơ**, không phải hướng giải quyết. Cast unchecked có thể đánh lừa hệ thống kiểu tĩnh và làm hỏng hợp đồng `List<Integer>`. Capture helper đúng cách **không cần unchecked cast**.

## 12. Các lỗi thường gặp khi đọc wildcard lồng nhau

**Lỗi 1 — Bỏ qua tầng có wildcard.** `List<List<?>>` và `List<? extends List<?>>` không có cùng quyền ghi lên danh sách ngoài. Một kiểu cho thêm một `List<X>` phù hợp; kiểu còn lại không.

**Lỗi 2 — Suy ra quan hệ subtype xuyên qua hai tầng generic bất biến.** Từ `List<Integer> <: List<? extends Number>` không được suy ra `List<List<Integer>> <: List<List<? extends Number>>`. Muốn mở rộng đầu vào ở tầng ngoài, cần một wildcard ở đúng tầng đó.

**Lỗi 3 — Nhìn thấy hai dấu `?` thì mặc định chúng cùng kiểu.** `List<List<?>>` có thể chứa một hàng `List<String>` và một hàng `List<Integer>`. Đối số kiểu của hai hàng hoàn toàn có thể khác nhau.

**Lỗi 4 — Nghĩ capture helper có thể nhận thêm bất kỳ `Object`.** Helper `<E>` chỉ thao tác được với giá trị đã được chứng minh thuộc `E`; không thể biến một `Object` ngẫu nhiên thành `E` bằng suy luận.

**Lỗi 5 — Nghĩ capture của hàng đầu tự động mở quyền ghi lên danh sách ngoài.** Cấp ngoài và cấp trong có thể có hai kiểu ẩn khác nhau; capture phải gắn với đúng collection mà phép đọc/ghi đang thực hiện.

**Lỗi 6 — Nhầm wildcard với bất biến runtime.** `List<?>` hoặc `List<? extends Number>` không đồng nghĩa immutable. `remove` hoặc `clear` có thể hợp lệ về kiểu; `set` qua helper có thể hợp lệ; runtime lại tùy collection cho sửa hay không.

**Lỗi 7 — Dùng `List<Object>` để thay `List<?>`.** `List<Object>` chỉ chấp nhận đối số kiểu chính xác `Object`. Nó không là “dạng dễ ghi của mọi danh sách”; ép kiểu từ `List<String>` sang `List<Object>` thường là dấu hiệu sai thiết kế.

**Lỗi 8 — Quên điều kiện kích thước và khả năng sửa.** Helper hoán đổi phần tử nên kiểm tra có ít nhất hai phần tử trước khi đọc/ghi; `List.of(...)` vẫn ném ngoại lệ nếu muốn `set`. Compiler chỉ kiểm tra kiểu, không bảo đảm logic runtime.

## 13. Bài tập kiểm tra kiến thức

Giả sử có các biến trong một phương thức Java với `import java.util.*;`:

~~~java
List<List<Integer>> integers = new ArrayList<>();
integers.add(new ArrayList<>(List.of(1, 2)));

List<List<?>> mixed = new ArrayList<>();
List<? extends List<?>> upperOuter = integers;
List<? extends List<? extends Number>> upperBoth = integers;
~~~

Hãy xác định các biểu thức sau **biên dịch được hay không**, xét từng dòng độc lập:

| Biểu thức | Biên dịch? | Giải thích |
| --- | --- | --- |
| `mixed.add(List.of("A"));` | Có | Phần tử tầng ngoài có kiểu `List<?>` |
| `mixed.add(List.of(1, 2));` | Có | `List<Integer>` phù hợp `List<?>` |
| `mixed = integers;` | Không | Tầng ngoài invariant; `List<List<Integer>>` không là `List<List<?>>` |
| `upperOuter = integers;` | Có | Kiểu hàng `List<Integer>` phù hợp upper bound `List<?>` |
| `upperOuter.add(List.of(3));` | Không | Tầng ngoài có kiểu phần tử ẩn |
| `List<?> row = upperOuter.get(0);` | Có | Hàng đọc ra dùng được như `List<?>` |
| `Object x = upperOuter.get(0).get(0);` | Có | Phần tử tầng trong dùng được như `Object` |
| `upperBoth = integers;` | Có | Cả hai tầng upper bound đều phù hợp |
| `Number n = upperBoth.get(0).get(0);` | Có | Bảo đảm đọc như `Number` |
| `upperBoth.get(0).add(10);` | Không | Không biết kiểu phần tử của hàng |
| `upperBoth.add(List.of(10));` | Không | Không biết kiểu hàng thực của tầng ngoài |
| `mixed.get(0).add("X");` | Không | Tầng trong là `List<?>` |
| `mixed.get(0).clear();` | Có | Xóa không cần cung cấp giá trị của kiểu ẩn; runtime tùy collection |

Với bài tập, `mixed.get(0)` có thể ném `IndexOutOfBoundsException` khi chạy vì danh sách `mixed` ban đầu rỗng; bảng chỉ hỏi **khả năng biên dịch**. Trong phép gán `mixed = integers`, compiler chặn ngay cả khi tình cờ các hàng hiện tại trống hoặc cùng kiểu.

### Câu hỏi vận dụng

1. Vì sao việc dùng `List<? extends List<?>>` để đọc nhiều kiểu hàng là an toàn, trong khi thêm `List<String>` vào nó bị chặn?
2. Có thể dùng helper `<E> void swap(List<E> row)` để hoán đổi phần tử trong một hàng `List<?>` không? **Có**, vì đọc và ghi dùng cùng `E` được capture.
3. Có thể lấy phần tử từ hai hàng `List<?>` khác nhau rồi hoán đổi chéo mà không ràng buộc chung không? **Không thể bảo đảm**, vì hai kiểu ẩn có thể khác nhau.
4. Nếu chỉ muốn tính tổng `Number` từ `List<List<Integer>>`, nên dùng helper capture hay nested `extends`? **Nested `extends` là đủ**, vì chỉ cần đọc giá trị.
5. Tại sao `List<List<? extends Number>>` không nhận trực tiếp `List<List<Integer>>`? **Bởi generic ở tầng ngoài invariant**, dù kiểu hàng tương thích wildcard.

## 14. Kết luận và quy tắc thiết kế

Muốn dùng wildcard lồng nhau an toàn, hãy **đọc kiểu từ tầng ngoài vào tầng trong**, sau đó xác định thao tác ở tầng nào:

- `List<List<?>>`: danh sách ngoài có phần tử chính xác kiểu `List<?>`; có thể thêm những hàng `List<X>` phù hợp vào ngoài, nhưng mỗi hàng khi đọc ra vẫn có đối số kiểu ẩn.
- `List<? extends List<?>>`: nhận danh sách ngoài có kiểu hàng là subtype của `List<?>` (ví dụ `List<List<Integer>>`), nhưng không được thêm hàng không phải `null` qua góc nhìn wildcard.
- `List<? extends List<? extends Number>>`: nhận danh sách nhóm số subtype ở cả hai tầng và đọc phần tử như `Number`; không được tự ý ghi phần tử/hàng mới qua góc nhìn ấy.
- **Capture helper `<E>`** hữu ích khi cần thao tác với các giá trị **cùng kiểu ẩn từ chính một collection**. Nếu có nhiều collection độc lập, phải có quan hệ kiểu được khai báo rõ; capture không tự tạo quan hệ đó.

Giới hạn cốt lõi: **một wildcard là một kiểu cụ thể nhưng chưa biết; hai wildcard là hai điều chưa biết có thể khác nhau; mỗi tầng wildcard giữ ràng buộc riêng**. Capture giúp compiler theo dõi một kiểu ẩn nhất quán trong phạm vi nhỏ, không loại bỏ tính bất biến generic, không cho phép ghi sai subtype, và không thay đổi khả năng sửa của collection runtime.