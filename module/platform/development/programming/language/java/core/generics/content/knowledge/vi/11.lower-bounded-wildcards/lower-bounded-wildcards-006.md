# Quan hệ giữa `? super Integer` và `? super Number` trong Java Generics

Hai kiểu `List<? super Integer>` và `List<? super Number>` trông rất giống nhau, nhưng **không tương đương**. Vì `Integer` là kiểu con của `Number`, quan hệ tương thích giữa hai wildcard cận dưới đi theo hướng:

```text
Integer <: Number

List<? super Number>  <:  List<? super Integer>
          |                         |
          +-------- gán được ------>+
```

Có thể gán một giá trị kiểu `List<? super Number>` cho biến kiểu `List<? super Integer>`. **Chiều ngược lại không hợp lệ.** Đây là một hệ quả của quy tắc *type argument containment* đối với wildcard cận dưới (`super`), thường được mô tả trực quan là hành vi phản biến (*contravariant*) ở vị trí wildcard.

Phải hiểu đúng câu này: `List<T>` thông thường vẫn **bất biến**. Không có quy tắc `List<Number>` là kiểu con của `List<Integer>`. Tính linh hoạt ở đây xuất hiện vì cả hai vế đều dùng wildcard cận dưới, không phải vì Java biến toàn bộ generic thành phản biến.

Bài học cần làm rõ ba việc: đối số kiểu nào có thể nằm sau mỗi `? super`, hai kiểu wildcard chuyển đổi được theo hướng nào, và vì sao quyền thêm/đọc qua chúng khác nhau.

## 1. `? super T` có nghĩa là gì?

Trong Java, khai báo:

```java
List<? super Integer> integerSink;
```

nói rằng biến tham chiếu một `List<X>` với một kiểu đối số `X` chưa được biết chính xác, nhưng `X` là **`Integer` hoặc một kiểu cha của `Integer`**. Ví dụ những kiểu đối số phù hợp gồm `Integer`, `Number`, `Object` và cả những giao diện cha mà `Integer` triển khai, chẳng hạn `Comparable<Integer>` hoặc `java.io.Serializable`.

Ngược lại:

```java
List<? super Number> numberSink;
```

yêu cầu `X` là **`Number` hoặc một kiểu cha của `Number`**, chẳng hạn `Number`, `Object`, hoặc `java.io.Serializable`.

Điểm quan trọng: “kiểu cha” trong quan hệ subtype của Java không chỉ là class được kế thừa qua `extends` mà còn gồm interface được triển khai qua `implements`. Một danh sách `List<Serializable>` cũng nhận được `Number` vì `Number implements Serializable`.

Ví dụ minh họa (các biến nằm trong thân một phương thức, với các import từ `java.util` và `java.io.Serializable`):

```java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();
List<Serializable> serializables = new ArrayList<>();
List<Comparable<Integer>> comparables = new ArrayList<>();

List<? super Integer> a = integers;
List<? super Integer> b = numbers;
List<? super Integer> c = objects;
List<? super Integer> d = serializables;
List<? super Integer> e = comparables;

List<? super Number> f = numbers;
List<? super Number> g = objects;
List<? super Number> h = serializables;

// List<? super Number> invalid = integers;   // Không biên dịch.
// List<? super Number> invalid2 = comparables; // Không biên dịch.
```

`List<Integer>` không phù hợp với `List<? super Number>`: `Integer` là **kiểu con**, không phải kiểu cha của `Number`. `Comparable<Integer>` cũng không là kiểu cha của `Number`, dù nó là một interface mà `Integer` thực hiện.

Trong API thực tế, loại tham số này thường được dùng như một **đích nhận dữ liệu** (consumer): `? super T` cho phép truyền các giá trị kiểu `T` vào một collection có kiểu phần tử được khai báo rộng hơn.

## 2. Tập các kiểu đối số hợp lệ giải thích chiều quan hệ

Có thể xem mỗi wildcard cận dưới như một điều kiện đặt lên đối số kiểu thực tế:

- Với `? super Integer`: đối số phải là `Integer` **hoặc một kiểu cha của `Integer`**.
- Với `? super Number`: đối số phải là `Number` **hoặc một kiểu cha của `Number`**.

Vì mọi kiểu cha của `Number` cũng là kiểu cha của `Integer` (do `Integer extends Number`), nên tập các kiểu đối số thỏa `? super Number` **nằm trong** tập thỏa `? super Integer`.

```text
Các đối số ví dụ được chấp nhận bởi ? super Integer:
    Integer, Number, Object, Serializable, Comparable<Integer>, ...

Các đối số ví dụ được chấp nhận bởi ? super Number:
             Number, Object, Serializable, ...

Tập (? super Number) là tập con của (? super Integer)
```

Đây là cách trực quan để hiểu vì sao một `List<? super Number>` có thể được nhìn qua tham chiếu `List<? super Integer>`: nếu collection được bảo đảm nhận `Number` thì tất nhiên nó cũng nhận mọi `Integer`.

Tuy nhiên, sơ đồ tập hợp trên chỉ minh họa điều kiện đối số kiểu, không phải định nghĩa hình thức rằng wildcard là một collection runtime hay hai danh sách được “chuyển đổi” thành nhau. Kiểm tra tương thích thực hiện tại **thời điểm biên dịch**, dựa trên luật bao hàm đối số kiểu (*containment*) và quy tắc gán của Java.

## 3. Gán một `List<? super Number>` cho `List<? super Integer>`

Ví dụ tối giản:

```java
List<? super Number> numberSink = new ArrayList<Number>();
List<? super Integer> integerSink = numberSink; // Hợp lệ.
```

Giải thích theo hợp đồng:

1. `numberSink` nhận được mọi đối tượng `Number`, kể cả `Integer`, `Double`, `Long`.
2. `integerSink` chỉ yêu cầu nơi nhận được đối tượng `Integer`.
3. Một danh sách nhận được `Number` đáp ứng yêu cầu nhận `Integer`, nên phép gán an toàn.

Nhưng sau phép gán, **quyền thao tác được xác định theo kiểu tĩnh của từng biến**:

```java
numberSink.add(1);
numberSink.add(2.5); // Hợp lệ: Double là Number.

integerSink.add(3);  // Hợp lệ: Integer.
// integerSink.add(4.5); // Không biên dịch: kiểu tĩnh là ? super Integer.
```

Dù cả hai biến trỏ đến cùng đối tượng danh sách, compiler không tự “nhớ” rằng `integerSink` được khởi tạo từ `numberSink`. Một khi tham chiếu được khai báo là `List<? super Integer>`, nó chỉ cung cấp hợp đồng hẹp hơn: **thêm được `Integer`**.

### Ví dụ hoàn chỉnh

Lưu thành `SuperAssignmentDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class SuperAssignmentDemo {
    public static void main(String[] args) {
        List<? super Number> numberSink = new ArrayList<Number>();
        numberSink.add(2.5);

        List<? super Integer> integerSink = numberSink;
        integerSink.add(10);
        integerSink.add(20);

        // integerSink.add(3.5); // Không biên dịch.

        System.out.println(numberSink);
        System.out.println(integerSink);

        Object item = integerSink.get(0);
        System.out.println(item);
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```bash
javac SuperAssignmentDemo.java
java SuperAssignmentDemo
```

Kết quả:

```text
[2.5, 10, 20]
[2.5, 10, 20]
2.5
```

Hai biến in cùng nội dung vì trỏ đến cùng một `ArrayList`. Giá trị đọc từ `integerSink.get(0)` chỉ bảo đảm có kiểu tĩnh dùng được như `Object`, nên dù phần tử đầu là `Double`, lời gọi vẫn hoàn toàn an toàn.

## 4. Vì sao không được gán ngược lại?

Phép gán dưới đây bị từ chối:

```java
List<? super Integer> integerSink = new ArrayList<Integer>();
// List<? super Number> numberSink = integerSink; // LỖI BIÊN DỊCH.
```

Hãy thử tưởng tượng phép gán được cho phép:

```java
List<Integer> realList = new ArrayList<>();
List<? super Integer> integerSink = realList;

// GIẢ ĐỊNH SAI — Java từ chối dòng dưới:
// List<? super Number> numberSink = integerSink;

// Nếu dòng trên được phép:
 // numberSink.add(3.14); // Double là Number.
 // realList sẽ chứa Double dù phải là List<Integer>.
```

`List<? super Integer>` có thể trỏ đến `List<Integer>`. Một `List<Integer>` **không** được thêm một `Double`. Nhưng `List<? super Number>` có hợp đồng cho phép thêm `Double`. Gán ngược sẽ khiến compiler cho phép một thao tác có thể phá an toàn kiểu của danh sách thật.

Đây chính là lý do quan hệ chỉ có một chiều:

```text
List<? super Number>  --->  List<? super Integer>   ĐÚNG
List<? super Integer> --->  List<? super Number>    SAI
```

Không thể suy ra chiều gán từ tên kiểu nằm ngay sau `super` một cách máy móc. Phải hỏi: **kiểu tham chiếu đích hứa được thêm những đối tượng nào, và nguồn có bảo đảm khả năng ấy trong mọi trường hợp không?**

## 5. Bảng quyền thêm phần tử và đọc phần tử

| Kiểu biến | Một số kiểu danh sách thực tế có thể tham chiếu | Giá trị non-null có thể thêm qua biến | Kiểu an toàn khi đọc bằng `get` |
| --- | --- | --- | --- |
| `List<? super Integer>` | `List<Integer>`, `List<Number>`, `List<Object>`, `List<Serializable>`, ... | `Integer` | `Object` |
| `List<? super Number>` | `List<Number>`, `List<Object>`, `List<Serializable>`, ... | `Number` và các kiểu con (`Integer`, `Double`, ...) | `Object` |
| `List<Integer>` | `List<Integer>` | `Integer` | `Integer` |
| `List<Number>` | `List<Number>` | `Number` và các kiểu con | `Number` |
| `List<?>` | Bất kỳ `List<T>` phù hợp | Không thêm tùy ý một giá trị non-null | `Object` |

Cả hai wildcard `? super` đều cho phép truyền **literal `null`** về mặt hệ kiểu; nhưng việc collection thật có hỗ trợ `add` và chấp nhận `null` là vấn đề riêng.

### 5.1. Quyền ghi (`add`)

Với `List<? super Number>`, compiler có thể khẳng định mọi danh sách hợp lệ đều nhận `Number` và các kiểu con:

```java
static void addNumbers(List<? super Number> target) {
    target.add(1);    // Integer là Number.
    target.add(2.5);  // Double là Number.
    target.add(3L);   // Long là Number.
}
```

Với `List<? super Integer>`, compiler chỉ bảo đảm nhận `Integer`. `Integer` là class `final`, nên không có class con để bổ sung vào lựa chọn này:

```java
static void addIntegers(List<? super Integer> target) {
    target.add(1);
    target.add(2);

    // target.add(2.5); // Không biên dịch.
}
```

Hai đoạn là phương thức minh họa, cần đặt trong một class có `import java.util.List;` nếu biên dịch riêng.

Lưu ý: “biên dịch được” khác “chắc chắn thêm thành công”. Một `List.of(...)` không sửa đổi vẫn có thể phù hợp về kiểu để truyền vào phương thức trên, nhưng `add` sẽ ném `UnsupportedOperationException`. Quy tắc generic xác định tương thích kiểu, không bảo đảm tính khả biến (*mutability*) của collection.

### 5.2. Quyền đọc (`get`)

`? super Number` không có nghĩa đọc được `Number`. Một `List<? super Number>` có thể trỏ đến `List<Object>`, hoặc `List<Serializable>` chứa đối tượng không phải `Number`. Vì thế:

```java
List<? super Number> numbers = new ArrayList<Object>();
Object first = numbers.isEmpty() ? null : numbers.get(0); // Hợp lệ.

// Number n = numbers.get(0); // Không biên dịch.
```

Tương tự:

```java
List<? super Integer> integers = new ArrayList<Number>();
Object first = integers.isEmpty() ? null : integers.get(0);

// Integer i = integers.get(0); // Không biên dịch.
```

Cận dưới cung cấp bảo đảm về **đối tượng có thể đưa vào**, không cung cấp bảo đảm chặt hơn `Object` cho **đối tượng lấy ra**. Khi cần đọc số và gọi `doubleValue()`, dùng `List<? extends Number>` (producer) hoặc `List<Number>` nếu phù hợp, thay vì dựa vào `? super Number`.

## 6. Ví dụ đầy đủ: dùng hai phương thức consumer

Lưu thành `LowerBoundConsumerDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class LowerBoundConsumerDemo {
    static void putIntegers(List<? super Integer> destination) {
        destination.add(10);
        destination.add(20);
    }

    static void putNumbers(List<? super Number> destination) {
        destination.add(30);
        destination.add(4.5);
    }

    public static void main(String[] args) {
        List<Integer> integers = new ArrayList<>();
        List<Number> numbers = new ArrayList<>();
        List<Object> objects = new ArrayList<>();

        putIntegers(integers);
        putIntegers(numbers);
        putIntegers(objects);

        putNumbers(numbers);
        putNumbers(objects);

        // putNumbers(integers); // LỖI BIÊN DỊCH.

        System.out.println("integers=" + integers);
        System.out.println("numbers=" + numbers);
        System.out.println("objects=" + objects);
    }
}
```

```bash
javac LowerBoundConsumerDemo.java
java LowerBoundConsumerDemo
```

Kết quả:

```text
integers=[10, 20]
numbers=[10, 20, 30, 4.5]
objects=[10, 20, 30, 4.5]
```

Vì `putIntegers` chỉ thêm `Integer`, bất kỳ `List<Integer>`, `List<Number>` hoặc `List<Object>` đều đủ khả năng nhận. `putNumbers` còn có thể thêm `Double`, nên `List<Integer>` không đáp ứng hợp đồng.

Cùng một đối tượng `List<Number>` có thể truyền cho cả hai phương thức, vì nó đủ rộng để nhận mọi `Number`. Điều đó không làm cho `List<Integer>` và `List<Number>` trở thành kiểu con của nhau.

## 7. Phép gán theo chiều `super` là quan hệ kiểu, không phải chuyển dữ liệu

Xét:

```java
List<Number> source = new ArrayList<>();
List<? super Number> numberSink = source;
List<? super Integer> integerSink = numberSink;
```

Ba biến cùng trỏ tới **một đối tượng**, không có thao tác chuyển đổi các phần tử sang kiểu khác, không tạo danh sách mới, và không duyệt collection.

`numberSink` cho phép thêm `Number`; `integerSink` chỉ cho phép thêm `Integer`. Nếu dữ liệu được thêm qua `numberSink` thì có thể quan sát nó qua `integerSink` bằng `get`, nhưng chỉ dưới kiểu `Object`.

Đây là bản chất của **cách nhìn (view) theo kiểu tĩnh**: cùng đối tượng runtime có thể được tham chiếu qua những khai báo generic có hợp đồng khác nhau. Compiler áp dụng hợp đồng của từng biến tại nơi sử dụng.

Một ví dụ ngắn:

```java
numberSink.add(1.5);
integerSink.add(2);
System.out.println(source); // [1.5, 2]
```

Nếu khai báo `integerSink` được phép “tự hiểu” nó luôn là `List<Number>` vì từng được gán từ `numberSink`, quy tắc sẽ trở nên phụ thuộc lịch sử gán của biến và không an toàn cho các giá trị khác đến từ tham số phương thức. Java kiểm tra theo loại tĩnh của biểu thức tại vị trí dùng.

## 8. `? super Number` và `? super Integer` không phải `List<Number>` hay `List<Integer>`

Phân biệt hai nhóm:

**Kiểu tham số hóa chính xác:**

```java
List<Number> exactNumbers = new ArrayList<>();
List<Integer> exactIntegers = new ArrayList<>();

// List<Number> invalid = exactIntegers; // Không biên dịch.
```

**Kiểu tham số hóa có wildcard:**

```java
List<? super Integer> anyIntegerDestination = exactIntegers;
List<? super Integer> anotherIntegerDestination = exactNumbers;

List<? super Number> anyNumberDestination = exactNumbers;
```

Cũng không được gán wildcard ngược thành đối số cụ thể:

```java
List<? super Number> wildcard = new ArrayList<Number>();

// List<Number> exact = wildcard; // Không biên dịch.
```

Lý do: biến `wildcard` còn có thể chứa một `List<Object>` hoặc `List<Serializable>`, vì vậy compiler không thể bảo đảm đối tượng thật có kiểu chính xác `List<Number>`. Việc nó được khởi tạo ngay trong ví dụ bằng `new ArrayList<Number>()` không thay đổi hợp đồng của biến `wildcard`.

Tương tự, `List<? super Integer>` không phải `List<Integer>` và cũng không tự trở thành `List<Number>`.

## 9. Liên hệ trực tiếp với nguyên tắc PECS

PECS viết tắt của **Producer Extends, Consumer Super**:

- **Producer:** tham số cung cấp đối tượng cho chương trình (chủ yếu đọc) → dùng `? extends T` khi phù hợp.
- **Consumer:** tham số nhận những đối tượng do chương trình đưa vào (chủ yếu ghi) → dùng `? super T` khi phù hợp.

Hãy xác định loại giá trị cụ thể phương thức cần **ghi** trước khi chọn cận dưới:

| Nhu cầu của phương thức | Kiểu tham số thích hợp | Lý do |
| --- | --- | --- |
| Thêm các `Integer` | `List<? super Integer>` | Nhận được `List<Integer>`, `List<Number>`, `List<Object>` và các supertypes khác |
| Thêm nhiều loại `Number` | `List<? super Number>` | Cho phép ghi `Integer`, `Double`, `Long`, ... |
| Chỉ đọc các đối tượng `Number` | `List<? extends Number>` | Đọc ra chắc chắn dùng được như `Number` |
| Vừa đọc vừa ghi chính xác một kiểu `T` | `List<T>` hoặc generic method | Giữ quan hệ giữa kiểu phần tử đọc ra và kiểu phần tử ghi vào |

Ví dụ nếu phương thức thực tế chỉ thêm `Integer` nhưng khai báo tham số `List<? super Number>`, nó vô tình loại bỏ `List<Integer>` khỏi tập caller hợp lệ. Khi đổi sang `List<? super Integer>`, API **rộng hơn về các loại danh sách có thể nhận**, trong khi vẫn đảm bảo lời gọi `add(Integer)` an toàn.

Ngược lại, nếu nội dung phương thức cần thêm `Double` và `Integer`, chuyển nó từ `List<? super Number>` sang `List<? super Integer>` sẽ khiến code bên trong không còn biên dịch. Chọn cận dưới căn cứ vào **loại giá trị cần ghi**, không dựa vào quan hệ kế thừa giữa những kiểu được đặt tên một cách tùy tiện.

## 10. Một phương thức có thể nhận `? super Integer` nhưng truyền tiếp sang `? super Number` không?

Giả sử có hai API:

```java
static void acceptIntegers(List<? super Integer> target) {
    target.add(100);
}

static void acceptNumbers(List<? super Number> target) {
    target.add(1.25);
}
```

Ta có thể viết:

```java
static void forwardNumbers(List<? super Number> target) {
    acceptIntegers(target); // Hợp lệ.
    acceptNumbers(target);  // Hợp lệ.
}
```

Nhưng chiều ngược lại không hợp lệ:

```java
static void forwardIntegers(List<? super Integer> target) {
    acceptIntegers(target); // Hợp lệ.
    // acceptNumbers(target); // Không biên dịch.
}
```

Tại sao? `forwardIntegers` có thể nhận trực tiếp `List<Integer>`. Nếu nó gọi `acceptNumbers`, phương thức kia có thể thêm `Double` vào danh sách thật sự chỉ chứa `Integer`. Compiler cấm chuyển tiếp nguy hiểm này.

Đây là tình huống rất thường gặp khi kết nối các hàm service hoặc helper: một API dùng cận dưới **rộng hơn về loại giá trị nó ghi** yêu cầu đích có khả năng tiếp nhận nhiều kiểu hơn, vì thế chỉ có thể nhận một tập đối số caller **hẹp hơn**.

## 11. Generic method và `Collections.copy`: áp dụng hai chiều dữ liệu

Một ví dụ thực tế về kết hợp producer/consumer là sao chép phần tử từ source sang destination. Phương thức Java có thể viết:

```java
static <T> void appendAll(
        List<? extends T> source,
        List<? super T> destination) {
    for (T item : source) {
        destination.add(item);
    }
}
```

Nếu source là `List<Integer>`, destination có thể là `List<Integer>`, `List<Number>` hoặc `List<Object>`. Nếu source là `List<Number>` có chứa cả `Double`, destination cần đủ khả năng nhận các `Number`.

Lưu thành `AppendAllDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class AppendAllDemo {
    static <T> void appendAll(
            List<? extends T> source,
            List<? super T> destination) {
        for (T value : source) {
            destination.add(value);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2);
        List<Number> numbers = new ArrayList<>();
        List<Object> objects = new ArrayList<>();

        appendAll(integers, numbers);
        appendAll(numbers, objects);

        System.out.println(numbers);
        System.out.println(objects);
    }
}
```

```bash
javac AppendAllDemo.java
java AppendAllDemo
```

Kết quả:

```text
[1, 2]
[1, 2]
```

Phương thức là ví dụ minh họa cùng quy tắc với chữ ký `Collections.copy(List<? super T> dest, List<? extends T> src)`, nhưng **hành vi khác nhau**: `appendAll` dùng `add` để nối phần tử và tăng kích thước, trong khi `Collections.copy` thay thế các phần tử đang có trong đích và yêu cầu đích đủ dài. Không thay thế lẫn nhau một cách máy móc.

Chỉ cần nhớ quan hệ khi chọn `T`: destination phải có kiểu phần tử là `T` hoặc kiểu cha của `T`. Nếu `T` là `Number`, một `List<Integer>` không thể nhận toàn bộ `Number`; nếu `T` là `Integer`, `List<Number>` hoàn toàn nhận được.

## 12. Bẫy do cách hiểu “super” theo tiếng tự nhiên

Một câu suy luận sai khá phổ biến:

> “`Number` là kiểu cha của `Integer`, vậy `List<? super Number>` chắc phải bao trùm nhiều loại danh sách hơn `List<? super Integer>`.”

Thực tế, yêu cầu `X super Number` **khắt khe hơn** yêu cầu `X super Integer`. Chỉ những `X` rộng đến mức chứa được mọi `Number` mới thỏa `? super Number`, trong khi `? super Integer` chỉ cần `X` rộng đủ để chứa mọi `Integer`.

Ví dụ:

```java
List<Integer> onlyIntegers = new ArrayList<>();

List<? super Integer> accepted = onlyIntegers; // Đúng.
// List<? super Number> rejected = onlyIntegers; // Sai.
```

`List<? super Integer>` **chấp nhận nhiều loại đối số kiểu thực tế hơn** (ví dụ có thể nhận `List<Integer>` và `List<Number>`), nhưng **cho phép thêm ít loại giá trị hơn** qua biến (`Integer` thay vì mọi `Number`).

Ngược lại, `List<? super Number>` **chấp nhận ít loại danh sách thực tế hơn**, nhưng **cho phép thêm nhiều loại giá trị hơn** (`Integer`, `Double`, `Long`, ...).

Đây là cặp đánh đổi quan trọng:

| Khía cạnh | `? super Integer` | `? super Number` |
| --- | --- | --- |
| Cận dưới | `Integer` | `Number` |
| Các danh sách caller hợp lệ | Rộng hơn | Hẹp hơn |
| Giá trị non-null có thể ghi | Chỉ `Integer` | Mọi `Number` (và kiểu con) |
| Đọc ra an toàn | `Object` | `Object` |
| Chuyển thành biến kiểu kia | Không tự chuyển sang `? super Number` | Có thể chuyển sang `? super Integer` |

## 13. Các lỗi biên dịch thường gặp và cách sửa

### Lỗi 1: đảo chiều phép gán

```java
List<? super Integer> ints = new ArrayList<Integer>();
// List<? super Number> nums = ints; // Sai.
```

**Cách sửa:** nếu code cần ghi các giá trị `Number` nói chung, hãy yêu cầu ngay từ đầu một đích có kiểu `List<? super Number>`. Nếu code chỉ cần ghi `Integer`, giữ `List<? super Integer>`.

### Lỗi 2: cho rằng `List<? super Integer>` luôn là `List<Number>`

```java
List<? super Integer> target = new ArrayList<Integer>();
// List<Number> exact = target; // Sai.
```

**Cách sửa:** nếu chương trình cần một `List<Number>` thật, tạo hoặc nhận một danh sách khai báo chính xác `List<Number>`. Wildcard không cho biết kiểu đối số cụ thể của danh sách thật.

### Lỗi 3: đọc từ `? super Number` rồi gọi ngay API của `Number`

```java
List<? super Number> target = new ArrayList<Object>();
// Number value = target.get(0); // Sai.
Object value = target.isEmpty() ? null : target.get(0); // Đúng.
```

**Cách sửa:** nếu nhiệm vụ là đọc các `Number` để tính toán, cân nhắc `List<? extends Number>`; nếu cần kiểu phần tử chính xác của nguồn, dùng generic method phù hợp. Không ép kiểu một cách mù quáng.

### Lỗi 4: suy từ kiểu biến sang khả năng sửa đổi runtime

```java
List<? super Number> target = List.of(1, 2);
// target.add(3.5); // Biên dịch được nếu bỏ comment, nhưng runtime ném
                   // UnsupportedOperationException.
```

**Cách sửa:** chỉ gọi `add` khi hợp đồng nguồn dữ liệu đảm bảo collection có thể sửa được; có thể dùng một `ArrayList` đích mới khi cần sở hữu và cập nhật danh sách.

### Lỗi 5: nghĩ `? super T` bảo đảm mọi phần tử hiện hữu là `T`

```java
List<Object> rawContents = new ArrayList<>();
rawContents.add("not a number");

List<? super Number> numbers = rawContents;
numbers.add(42);

Object first = numbers.get(0); // "not a number", không phải Number.
```

**Cách sửa:** quan hệ cận dưới chỉ xác định đối tượng **có thể thêm**, không giới hạn những đối tượng đã có trong một danh sách kiểu cha. Nếu cần mọi phần tử là `Number`, một khai báo source kiểu `List<? extends Number>` hoặc `List<Number>` mới phù hợp.

### Lỗi 6: ép kiểu để lách quan hệ gán

Ví dụ cố ép `(List<? super Number>) (List<?>) integerList` đánh mất bằng chứng an toàn kiểu và có thể tạo cảnh báo `unchecked`. Nếu thêm `Double` vào danh sách thật `List<Integer>`, lỗi có thể phát sinh muộn khi đọc dưới kiểu `Integer`. Không dùng raw type hoặc cast unchecked để “sửa” lỗi gán wildcard.

## 14. Kiểm tra kiến thức

**Câu 1.** `Integer extends Number`; phép gán nào hợp lệ?

```java
List<? super Number> nums = new ArrayList<Number>();
List<? super Integer> ints = nums; // Đúng.

// List<? super Number> other = ints; // Sai.
```

Lời gán đầu tiên đúng vì mọi nơi nhận `Number` đều nhận `Integer`. Lời gán ngược sai vì `ints` có thể chỉ là `List<Integer>`.

**Câu 2.** `List<? super Integer>` có truyền được vào `void addNumbers(List<? super Number> x)` không?

**Không**, vì phương thức có thể thêm `Double`. Nhưng `List<? super Number>` có truyền được vào `void addIntegers(List<? super Integer> x)`.

**Câu 3.** `List<? super Number>` cho đọc ra một biến `Number` không?

**Không có bảo đảm đó.** Danh sách thật có thể là `List<Object>` có các đối tượng không phải `Number`. Chỉ chắc chắn đọc được như `Object`.

**Câu 4.** `List<Serializable>` có phù hợp với `List<? super Number>` không?

**Có**, vì class `Number` triển khai `Serializable`. Cận dưới xét cả quan hệ interface, không chỉ chuỗi superclass.

**Câu 5.** `List<? super Integer>` có “mạnh hơn” hay “yếu hơn” `List<? super Number>`?

Không có một từ duy nhất mô tả mọi thao tác. `? super Integer` nhận được **nhiều loại đích hơn** nhưng chỉ bảo đảm ghi `Integer`; `? super Number` nhận **ít loại đích hơn** nhưng cho ghi mọi `Number`. Về chiều gán, `List<? super Number>` tương thích với `List<? super Integer>`.

## 15. Quy tắc ghi nhớ

1. Nếu `A` là kiểu con của `B`, thì theo hướng wildcard cận dưới: `List<? super B>` có thể gán cho `List<? super A>`.
2. `List<? super Integer>` nhận các danh sách có kiểu phần tử là `Integer` hoặc một kiểu cha của `Integer`. Nó cho ghi `Integer`.
3. `List<? super Number>` nhận các danh sách có kiểu phần tử là `Number` hoặc một kiểu cha của `Number`. Nó cho ghi mọi `Number`.
4. Cả hai kiểu đều chỉ bảo đảm đọc phần tử dưới dạng `Object`.
5. Generic chính xác như `List<Integer>` và `List<Number>` vẫn bất biến, không tự có quan hệ kế thừa theo đối số kiểu.
6. Chọn cận `super` theo **loại giá trị hàm cần thêm**, đồng thời kiểm tra riêng khả năng sửa đổi của collection runtime.

Cách tự kiểm tra nhanh nhất trước mỗi phép gán là đặt câu hỏi: “Nếu chương trình chỉ biết kiểu biến ở **vế trái**, nó được phép thêm đối tượng nào, và danh sách ở **vế phải** có chắc nhận được mọi đối tượng đó không?” Nếu câu trả lời luôn có, phép gán mới an toàn về kiểu.