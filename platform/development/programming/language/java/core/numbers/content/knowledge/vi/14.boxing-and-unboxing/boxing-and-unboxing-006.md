# `List<Integer>` không phải `int[]` trong Java

Trong Java, `int[]` là **mảng các giá trị nguyên thủy `int`**, còn `List<Integer>` là **kiểu danh sách tham chiếu đến các đối tượng `Integer`**. Cả hai có thể biểu diễn dãy số như 2, 4, 6, nhưng chúng **không có cùng kiểu, cách lưu trữ, API, khả năng thay đổi kích thước, cách xử lý `null` và chi phí thao tác**.

```java
int[] array = {2, 4, 6};
java.util.List<Integer> list = new java.util.ArrayList<>();
list.add(2);
list.add(4);
list.add(6);

System.out.println(array[0]);  // 2
System.out.println(list.get(0)); // 2
```

Kết quả in giống nhau không có nghĩa hai biến có thể hoán đổi cho nhau. Đặc biệt, trong chủ đề **Boxing và unboxing**, `List<Integer>` còn liên quan đến chuyển đổi ngầm giữa `int` và `Integer`, cấp phát/giữ tham chiếu đối tượng, và nguy cơ `NullPointerException` khi unboxing.

## 1. Bảng so sánh nhanh

| Đặc điểm | `int[]` | `List<Integer>` |
| --- | --- | --- |
| Kiểu dữ liệu | Mảng của primitive `int` | Kiểu generic `List` với tham số kiểu tham chiếu `Integer` |
| Phần tử | Giá trị `int` 32 bit | Tham chiếu tới đối tượng `Integer` hoặc `null` nếu implementation cho phép |
| Lấy phần tử | `a[i]` | `list.get(i)` |
| Gán phần tử | `a[i] = value` | `list.set(i, value)` nếu list hỗ trợ |
| Số phần tử | `a.length` (trường) | `list.size()` (phương thức) |
| Tăng/giảm số phần tử | Không; độ dài mảng cố định | Phụ thuộc implementation: `ArrayList` thêm/xóa được; `List.of` không sửa được |
| Phần tử mặc định khi tạo vùng chứa | `new int[3]` chứa ba số 0 | `new ArrayList<Integer>()` rỗng; `new Integer[3]` chứa ba `null` |
| Chấp nhận `null` làm phần tử | Không | Có thể, ví dụ `ArrayList`, nhưng `List.of` cấm |
| Generic type argument | Không áp dụng | Phải dùng `Integer`, không thể viết `List<int>` |
| Mô hình truy cập | Truy cập chỉ số của mảng | Hợp đồng `List`; độ phức tạp phụ thuộc loại list |
| Thư viện thao tác | `Arrays.sort`, `Arrays.stream`, `Arrays.equals` | `sort`, `stream`, `contains`, `add`, `remove`... tùy khả năng sửa đổi |
| Mức sử dụng bộ nhớ | Phần tử `int` được lưu trong mảng primitive | Thường có vùng tham chiếu và các đối tượng wrapper, thêm chi phí quản lý |
| Tính tương thích kiểu | Không phải `Integer[]` hay `List<Integer>` | Không tự trở thành `int[]`, cần chuyển đổi chủ động |

**Cần nhớ:** `List<Integer>` chỉ định *kiểu phần tử*, **không chỉ định cấu trúc bên trong**. `ArrayList<Integer>` thường giữ tham chiếu trong một mảng `Object[]`, nhưng `LinkedList<Integer>` dùng các nút liên kết. Không được suy ra rằng mọi `List<Integer>` đều liên tục trong bộ nhớ hoặc có tốc độ truy cập chỉ số như mảng.

## 2. `int` là primitive, `Integer` là lớp wrapper

`int` không phải một object. `Integer` là một lớp bất biến của `java.lang` chứa giá trị `int` và cung cấp các API như `intValue`, `parseInt`, `compare`.

```java
int primitive = 42;
Integer wrapper = Integer.valueOf(42);
int restored = wrapper.intValue();
```

Java hỗ trợ **autoboxing** và **unboxing** nên nhiều phép chuyển đổi được viết ngắn hơn:

```java
Integer boxed = 42; // Autoboxing: int -> Integer.
int unboxed = boxed; // Unboxing: Integer -> int.
```

Khi thêm `int` vào `List<Integer>`, việc boxing xảy ra ngầm:

```java
java.util.List<Integer> values = new java.util.ArrayList<>();
values.add(10);       // Về ý nghĩa là thêm một Integer chứa 10.
int first = values.get(0); // get trả Integer; gán vào int -> unboxing.
```

**Không phải mọi thao tác `List<Integer>` đều boxing mới**: có thể thêm một tham chiếu `Integer` đã tồn tại; JVM cũng có thể dùng cache wrapper đối với một số giá trị. Vì vậy, nói “mỗi phần tử luôn tạo đúng một object mới” là không chính xác. Điều quan trọng là API làm việc với **đối tượng/tham chiếu**, khác với ô `int` primitive.

### Tại sao `List<int>` không hợp lệ?

Java generics truyền thống yêu cầu **type argument là kiểu tham chiếu**; primitive `int` không phải type argument hợp lệ:

```java
// List<int> bad = new ArrayList<>(); // Không biên dịch.

java.util.List<Integer> good = new java.util.ArrayList<>();
```

Java không tự biến `List<int>` thành `List<Integer>` ở cú pháp generic. Khi cần tính toán theo luồng primitive tránh boxing, Java cung cấp `IntStream`; khi cần dữ liệu primitive lưu liên tục, `int[]` thường là lựa chọn phù hợp hơn.

### `Integer[]` cũng không phải `int[]`

`Integer[]` là mảng **tham chiếu đến `Integer`**, có thể chứa `null`. Trong khi đó `int[]` là mảng chứa **giá trị `int`**. Hai kiểu mảng không tương thích bằng một phép cast thông thường:

```java
int[] primitives = {1, 2, 3};
Integer[] objects = {1, 2, 3}; // Mỗi giá trị được boxing.

// Integer[] wrong = primitives; // Không biên dịch.
// int[] wrong2 = objects;       // Không biên dịch.
```

`Integer[]` có phần tử và bộ nhớ khác `int[]`; nó gần với `List<Integer>` về kiểu đối tượng phần tử, nhưng vẫn là **mảng có độ dài cố định**, không phải List.

## 3. Khác biệt API: `length`, `size()`, `[]`, `get()`, `set()`

Với mảng:

```java
int[] ages = {18, 20, 22};
System.out.println(ages.length); // 3.
System.out.println(ages[1]);     // 20.
ages[1] = 21;
```

Với danh sách:

```java
java.util.List<Integer> ages =
        new java.util.ArrayList<>(java.util.List.of(18, 20, 22));

System.out.println(ages.size()); // 3.
System.out.println(ages.get(1)); // 20.
ages.set(1, 21);
```

Không thể dùng `ages.length` hoặc `ages[1]` khi `ages` có kiểu `List<Integer>`. Ngược lại, mảng không có `get`, `set`, `add` hoặc `size()` như `List`.

### Kích thước và khả năng sửa đổi là hai trục khác nhau

Mảng có độ dài cố định, nhưng **phần tử có thể sửa**:

```java
int[] nums = {1, 2};
nums[0] = 9; // Hợp lệ.
// nums.add(3); // Không có add.
```

`List<Integer>` chỉ là interface: nó có phương thức thay đổi dữ liệu nhưng implementation có thể **không hỗ trợ**. Ví dụ:

```java
java.util.List<Integer> resizable = new java.util.ArrayList<>();
resizable.add(1);
resizable.add(2); // Tăng size lên 2.

java.util.List<Integer> fixedValues = java.util.List.of(1, 2);
// fixedValues.add(3); // Ném UnsupportedOperationException lúc chạy.
// fixedValues.set(0, 9); // Cũng ném UnsupportedOperationException.
```

`List.of` (Java 9+) tạo danh sách **không sửa đổi được** (*unmodifiable*). Nó không cho thêm/xóa, cũng không cho thay phần tử và **không chấp nhận phần tử `null`**. `ArrayList` mặc định có thể thêm/xóa/set và có thể chứa `null`.

Không nên suy luận rằng `List<Integer>` luôn “có thể tăng kích thước”; điều đó chỉ đúng với một số triển khai và điều kiện hoạt động.

## 4. Tác động của `null` và unboxing

Đây là khác biệt quan trọng nhất về độ an toàn.

`new int[3]` tạo **ba giá trị 0**. Mỗi phần tử của mảng primitive luôn là một `int` hợp lệ, không thể là `null`.

```java
int[] ints = new int[1];
System.out.println(ints[0]); // 0.
```

Ngược lại, mảng wrapper `new Integer[3]` có các phần tử mặc định bằng `null`, còn `new ArrayList<Integer>()` ban đầu có **size = 0**, không có phần tử nào:

```java
Integer[] objects = new Integer[1];
System.out.println(objects[0]); // null.

java.util.List<Integer> empty = new java.util.ArrayList<>();
System.out.println(empty.size()); // 0.
```

Danh sách cho phép `null` có thể gây lỗi khi bạn lấy giá trị primitive:

```java
java.util.List<Integer> list = new java.util.ArrayList<>();
list.add(null);

// int x = list.get(0); // Ném NullPointerException lúc unboxing.
Integer value = list.get(0);
System.out.println(value == null); // true.
```

Tương tự, `for (int x : list)` sẽ unbox từng `Integer` và có thể ném `NullPointerException` khi gặp `null`. `list.stream().mapToInt(Integer::intValue)` cũng không xử lý `null` một cách ngầm định.

**Thiết kế API:** nếu phần tử phải luôn có giá trị nguyên, có thể tránh `null` bằng validation hoặc dùng kiểu chứa primitive. Nếu `null` có nghĩa “chưa biết”, cần nêu rõ chính sách xử lý thay vì unboxing vô điều kiện hoặc tự động thay bằng 0 (vì 0 có thể là dữ liệu hợp lệ).

## 5. Vì sao hai vùng chứa không tương thích trực tiếp?

`int[]` là **một kiểu mảng runtime cụ thể** (array component type là primitive `int`). `List<Integer>` là **một đối tượng implements interface `List`**. Java không có chuyển đổi tự động giữa hai cấu trúc này:

```java
int[] raw = {1, 2, 3};

// List<Integer> list = raw; // Không biên dịch.
// int[] other = new ArrayList<Integer>(); // Không biên dịch.
```

Cả hai đều là object ở mức tham chiếu Java (mảng là object), nhưng **một mảng `int[]` không triển khai `List`**. Ép `(List<Integer>) raw` cũng không phải giải pháp; nó không chuyển dữ liệu thành wrapper và danh sách.

`List<Integer>` không có nghĩa “một mảng int với API khác”. Bất kỳ chuyển đổi thực sự nào phải duyệt phần tử, thực hiện boxing hoặc unboxing, và tạo cấu trúc đích phù hợp.

### Tính đa hình và generic invariance

`List<Integer>` **không phải subtype của** `List<Number>`, mặc dù `Integer extends Number`. Java generics có quy tắc *invariance* cho kiểu như `List<T>`:

```java
java.util.List<Integer> ints = java.util.List.of(1, 2);
// List<Number> numbers = ints; // Không biên dịch.

java.util.List<? extends Number> readOnlyView = ints;
Number x = readOnlyView.get(0);
```

`List<? extends Number>` cho phép đọc các phần tử như `Number`, nhưng không cho phép tùy tiện thêm các `Number` mới, bởi danh sách thật có thể chỉ chấp nhận `Integer`. Đây là vấn đề **generic type safety**, không liên quan đến khả năng ép `int[]` sang List.

Mảng đối tượng có quy tắc *covariance* khác generic và có thể phát sinh `ArrayStoreException` lúc chạy, nhưng `int[]` không phải subtype của `Object[]`: phần tử của `int[]` là primitive, không phải tham chiếu.

## 6. Bẫy phổ biến nhất: `Arrays.asList(int[])`

Nhiều người viết:

```java
int[] raw = {2, 4, 6};
var list = java.util.Arrays.asList(raw);
```

Điều bất ngờ: **`list` không phải `List<Integer>`**. Nó là `List<int[]>` có **đúng một phần tử là nguyên cả mảng `raw`**.

```java
System.out.println(list.size());      // 1.
System.out.println(list.get(0).length); // 3.
```

`Arrays.asList(T... a)` nhận varargs kiểu **tham chiếu** `T`. Với đối số `int[]`, bản thân `int[]` là một object; Java suy ra `T = int[]`. Không có quá trình tự “trải” từng số trong mảng primitive thành `Integer`.

Vì vậy:

```java
// List<Integer> wrong = Arrays.asList(new int[]{1,2,3});
// Lỗi biên dịch do kiểu suy ra không phù hợp.
```

Đừng cố sửa bằng raw type hoặc ép kiểu không an toàn: hậu quả có thể là `ClassCastException` khi lấy phần tử.

### `Arrays.asList(Integer[])` thì khác

```java
Integer[] objects = {2, 4, 6};
java.util.List<Integer> list = java.util.Arrays.asList(objects);

System.out.println(list.size()); // 3.
list.set(0, 10);
System.out.println(objects[0]); // 10.
```

Trong trường hợp này, mảng phần tử tham chiếu `Integer[]` được đưa vào `Arrays.asList`, nên danh sách nhận từng phần tử `Integer`. Danh sách trả về có **kích thước cố định** và **backed by** mảng `objects`:

- `list.set` làm thay đổi vị trí tương ứng trong mảng gốc.
- Thay đổi phần tử của mảng gốc được phản ánh qua danh sách.
- `list.add` và `list.remove` ném `UnsupportedOperationException` vì chúng thay đổi kích thước.

**Không nhầm `Arrays.asList` với `new ArrayList<>()`.** Cùng triển khai interface `List` nhưng có khả năng resize và quan hệ với mảng gốc rất khác nhau.

### `List.of(raw)` cũng không chuyển thành `List<Integer>`

Nếu `raw` là `int[]`, `List.of(raw)` tạo một danh sách chứa **một phần tử là mảng `int[]`**, không phải danh sách boxed integers. Khi cần boxed list, hãy dùng stream `boxed()` hoặc vòng lặp.

## 7. Chuyển từ `int[]` sang `List<Integer>`

### Cách 1 — Vòng lặp và `ArrayList` (danh sách thay đổi được)

```java
int[] raw = {2, 4, 6};
java.util.List<Integer> list = new java.util.ArrayList<>();

for (int value : raw) {
    list.add(value); // Autoboxing int -> Integer.
}
```

Đây là cách dễ hiểu và hoạt động với Java 17+. Nó tạo một danh sách **độc lập** với mảng gốc: thay `list.set(0, 99)` **không** sửa `raw[0]`, và thay `raw[0]` **không** sửa danh sách đã tạo.

Đối với dữ liệu lớn, có thể đặt dung lượng dự kiến:

```java
java.util.ArrayList<Integer> list =
        new java.util.ArrayList<>(raw.length);
for (int value : raw) {
    list.add(value);
}
```

`new ArrayList<>(raw.length)` chỉ chọn **initial capacity**; nó chưa tạo `raw.length` phần tử và `size()` ban đầu vẫn là 0. Không dùng `set(i, value)` ngay nếu chưa có phần tử ở index `i`.

### Cách 2 — `Arrays.stream(...).boxed()`

```java
int[] raw = {2, 4, 6};
java.util.List<Integer> list =
        java.util.Arrays.stream(raw).boxed().toList();
```

`Arrays.stream(raw)` tạo `IntStream` nhận các `int`. `boxed()` chuyển thành `Stream<Integer>`; `toList()` của Stream (có từ Java 16) trả về danh sách **unmodifiable**. Do đó `list.add(8)`/`list.set(0,9)` sẽ ném `UnsupportedOperationException`.

Nếu muốn danh sách sửa được:

```java
java.util.List<Integer> mutable =
        new java.util.ArrayList<>(
                java.util.Arrays.stream(raw).boxed().toList());
mutable.add(8);
```

Đừng giả định một cách chung rằng mọi terminal operation thu danh sách đều trả `ArrayList` có thể sửa. Hợp đồng mutability phải được kiểm tra rõ.

### Dùng `List.of` cho từng số biết trước

```java
java.util.List<Integer> values = java.util.List.of(2, 4, 6);
```

Ở đây từng đối số `int` được boxing để trở thành `Integer`. Kết quả là danh sách không sửa đổi được. Dạng này tiện cho dữ liệu cấu hình ngắn, **không** đồng nghĩa `List.of(new int[]{2,4,6})`.

## 8. Chuyển từ `List<Integer>` về `int[]`

### Cách 1 — Duyệt và unbox thủ công

```java
java.util.List<Integer> list = java.util.List.of(2, 4, 6);
int[] raw = new int[list.size()];

for (int i = 0; i < list.size(); i++) {
    raw[i] = list.get(i); // Integer -> int.
}
```

Với `ArrayList`, `get(i)` thường là O(1), nên cách này phù hợp. Nhưng với một số `List` khác như `LinkedList`, truy cập index `get(i)` nhiều lần có thể tốn O(n²) tổng cộng. Nếu không biết implementation hoặc muốn code dùng chung, nên dùng enhanced-for:

```java
int[] raw = new int[list.size()];
int i = 0;
for (Integer value : list) {
    raw[i++] = value; // Unboxing, có thể ném NPE nếu value là null.
}
```

Nếu List có thể bị sửa đồng thời, việc lấy `size()` trước rồi duyệt không tự bảo đảm snapshot nhất quán. Phải có hợp đồng đồng bộ/snapshot phù hợp với ứng dụng.

### Cách 2 — Stream `mapToInt`

```java
java.util.List<Integer> list = java.util.List.of(2, 4, 6);

int[] raw = list.stream()
        .mapToInt(Integer::intValue)
        .toArray();
```

`mapToInt(Integer::intValue)` thực hiện unboxing/chuyển sang `int`. Nếu danh sách chứa `null`, việc gọi `intValue` trên `null` sẽ ném `NullPointerException`.

Nếu nghiệp vụ muốn bỏ qua `null`, phải viết rõ, chẳng hạn:

```java
int[] nonNullOnly = list.stream()
        .filter(java.util.Objects::nonNull)
        .mapToInt(Integer::intValue)
        .toArray();
```

Nhưng việc **lọc mất phần tử** có thể thay đổi quan hệ vị trí, nên không áp dụng tùy tiện cho index, mẫu đo hay dữ liệu có thứ tự cố định. Trong nhiều API, từ chối `null` với lỗi rõ ràng là an toàn hơn.

### `toArray` không tạo `int[]`

```java
java.util.List<Integer> list = java.util.List.of(2, 4, 6);
Integer[] boxedArray = list.toArray(new Integer[0]); // Đúng: Integer[].
```

Phương thức `List.toArray` làm việc với **mảng đối tượng**; không có một cách gọi `toArray(new int[0])` để tự unbox toàn bộ. Nếu cần `int[]`, dùng vòng lặp hoặc `mapToInt(...).toArray()`.

## 9. Các lỗi chỉ xuất hiện khi sử dụng API tập hợp

### `remove(1)` không giống `remove(Integer.valueOf(1))`

`List<Integer>` có hai overload:

- `remove(int index)` — xóa theo **chỉ số**.
- `remove(Object o)` — xóa theo **giá trị** bằng quy tắc equality của đối tượng.

```java
java.util.List<Integer> nums =
        new java.util.ArrayList<>(java.util.List.of(10, 20, 30));

nums.remove(1);                  // Xóa phần tử tại index 1 (giá trị 20).
System.out.println(nums);       // [10, 30].

nums.remove(Integer.valueOf(30)); // Xóa theo giá trị 30.
System.out.println(nums);          // [10].
```

`nums.remove(1)` chọn overload `remove(int)`, không phải “xóa số 1”. Nếu cần xóa giá trị 1, viết `nums.remove(Integer.valueOf(1))` hoặc ép rõ `remove((Object) 1)` sau khi cân nhắc boxing.

Với `int[]` không có `remove`; muốn loại phần tử cần tạo mảng mới hoặc tự quản lý một đoạn hợp lệ trong mảng.

### So sánh `Integer` bằng `==` có bẫy tham chiếu

`Integer` là object; hai tham chiếu có thể chỉ vào cùng wrapper hoặc không. Java cache một số giá trị boxed; không dựa vào cache để làm equality:

```java
Integer a = Integer.valueOf(1000);
Integer b = Integer.valueOf(1000);

System.out.println(a.equals(b)); // true.
```

Không nên dùng `a == b` để kiểm tra hai wrapper có cùng **giá trị số**. Nó so sánh **định danh đối tượng** khi cả hai toán hạng là `Integer` (và không có unboxing do ngữ cảnh). Với `Integer` có thể `null`, dùng `java.util.Objects.equals(a,b)` khi muốn equality null-safe.

### `Arrays.equals` khác `List.equals`

`int[]` không override `equals` để so sánh từng phần tử; `array1.equals(array2)` là so sánh tham chiếu theo `Object`. Để so nội dung:

```java
int[] x = {1, 2};
int[] y = {1, 2};
System.out.println(java.util.Arrays.equals(x, y)); // true.
```

`List.equals`, ngược lại, được định nghĩa theo thứ tự và equality của các phần tử:

```java
java.util.List<Integer> x = java.util.List.of(1, 2);
java.util.List<Integer> y = new java.util.ArrayList<>(x);
System.out.println(x.equals(y)); // true.
```

`Arrays.equals(int[],int[])` và `List.equals` là hai API khác nhau, không có phép equals mặc định liên kiểu giữa `int[]` và `List<Integer>`.

## 10. Hiệu năng và bộ nhớ: khác biệt có ý nghĩa khi dữ liệu lớn

Với `int[]`, phần tử nguyên thủy dùng **4 byte mỗi giá trị `int`**, chưa tính phần header/căn chỉnh của mảng. Mảng chứa trực tiếp các giá trị, thường có tính locality tốt khi duyệt tuần tự.

Với `ArrayList<Integer>`:

- `ArrayList` thường lưu **tham chiếu** trong mảng `Object[]`, không phải 4 byte `int` trực tiếp trong backing array.
- `Integer` là một object wrapper; không gian lưu, cache và chính sách tối ưu JVM ảnh hưởng chi phí thực tế.
- Boxing/unboxing có thể có chi phí; boxing đôi khi tái sử dụng object cache hoặc được JVM tối ưu hóa, vì thế không nên tuyên bố “mỗi vòng lặp luôn cấp phát một object”.
- `ArrayList` còn quản lý capacity và có thể giữ chỗ chưa dùng.
- `LinkedList<Integer>` thường cần các node liên kết, dẫn đến đặc tính bộ nhớ/cache/truy cập khác `ArrayList`.

Kích thước chính xác trên heap phụ thuộc **JVM, pointer compression, layout, alignment, capacity, cache, vòng đời đối tượng và tối ưu JIT**. Không nên lấy một con số “`List<Integer>` tốn gấp X lần” làm chân lý cho mọi môi trường.

### Với hàng triệu số nguyên

Nếu bạn làm tính toán nguyên đơn giản trên hàng triệu phần tử và **không cần collection API** hay `null`, `int[]` thường có lợi về không gian và truy cập tuần tự. Ví dụ:

```java
long sum = 0L;
for (int value : data) {
    sum += value; // data là int[]; dùng long để giảm rủi ro tràn tổng int.
}
```

Đoạn này dùng `long` cho biến tổng nhưng tổng vẫn có thể tràn `long` nếu dữ liệu đủ lớn; tính toán chuẩn xác tuyệt đối đòi hỏi phân tích giới hạn miền.

Nếu cần thao tác thêm/xóa, thuật toán collection, các giao diện đa hình và sự thuận tiện của Java Collections, `List<Integer>` có thể hợp lý. Nhưng vì `List` là một interface, không thể suy ra hiệu năng chỉ từ tên kiểu khai báo.

### Benchmark đúng cách

Nếu tối ưu hiệu năng thực sự quan trọng, dùng benchmark như **JMH**, có warmup, đo nhiều lượt, kiểm soát kích thước dữ liệu và tránh compiler tối ưu loại bỏ công việc. Không kết luận từ một lần `System.nanoTime()` hoặc từ các vòng lặp quá nhỏ. Khi đo, phân biệt chi phí **khởi tạo/bộ nhớ**, **truy cập**, **boxing**, **GC** và **tần suất thay đổi kích thước**.

## 11. Duyệt, sắp xếp và Stream API

### Vòng lặp

Mảng:

```java
int[] arr = {3, 1, 2};
for (int value : arr) {
    System.out.println(value);
}
```

List:

```java
java.util.List<Integer> nums = java.util.List.of(3, 1, 2);
for (int value : nums) { // Mỗi Integer được unbox thành int.
    System.out.println(value);
}
```

Nếu List có `null`, vòng lặp `for (int value : nums)` có thể ném NPE. Dùng `for (Integer value : nums)` nếu cần xử lý nullable, và định nghĩa rõ ý nghĩa `null`.

### Sắp xếp

```java
int[] arr = {3, 1, 2};
java.util.Arrays.sort(arr); // Thay đổi mảng, kết quả {1,2,3}.
```

```java
java.util.List<Integer> nums =
        new java.util.ArrayList<>(java.util.List.of(3, 1, 2));
nums.sort(Integer::compareTo); // Thay đổi List có hỗ trợ set.
```

Sắp xếp List không sửa đổi được có thể ném `UnsupportedOperationException`. Nếu danh sách chứa `null`, comparator không hỗ trợ `null` có thể gây NPE; lựa chọn chính sách sắp xếp null cần minh bạch. Khi thiết kế comparator số nguyên, dùng `Integer.compare(a,b)` thay vì phép trừ `a-b` có thể overflow.

### Primitive stream và boxed stream

```java
int[] raw = {1, 2, 3};
int sum = java.util.Arrays.stream(raw).sum(); // IntStream.

java.util.List<Integer> list = java.util.List.of(1, 2, 3);
int otherSum = list.stream().mapToInt(Integer::intValue).sum();
```

`IntStream` chuyên cho primitive, giúp tránh một phần boxing trong chuỗi thao tác. `Stream<Integer>` vận hành trên wrapper và cần chuyển sang `IntStream` khi muốn các phép thống kê primitive như `sum`, `average` hoặc `summaryStatistics`.

**Cảnh báo về tràn:** `IntStream.sum()` trả `int`, có thể tràn như phép cộng `int`. Nếu cần tổng `long`, hãy map lên `long` trước:

```java
long total = java.util.Arrays.stream(raw).asLongStream().sum();
```

Với dữ liệu lớn vượt miền `long`, hãy cân nhắc `BigInteger`/kiểm tra tràn.

## 12. Ví dụ Java 17+ chạy độc lập

Lưu tệp `ListVsArrayDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class ListVsArrayDemo {
    public static void main(String[] args) {
        int[] raw = {2, 4, 6};
        List<Integer> boxed = new ArrayList<>();

        for (int n : raw) {
            boxed.add(n); // Boxing.
        }

        System.out.println("array length = " + raw.length);
        System.out.println("list size = " + boxed.size());

        boxed.set(0, 9);
        System.out.println("array first = " + raw[0]
                + ", list first = " + boxed.get(0));

        boxed.add(8);
        System.out.println("list after add = " + boxed);

        int[] unpacked = boxed.stream()
                .mapToInt(Integer::intValue)
                .toArray();
        System.out.println("unpacked = " + Arrays.toString(unpacked));

        List<Integer> streamList = Arrays.stream(raw).boxed().toList();
        System.out.println("stream boxed = " + streamList);
        try {
            streamList.add(8);
        } catch (UnsupportedOperationException ex) {
            System.out.println("toList is unmodifiable");
        }

        List<int[]> trap = Arrays.asList(raw);
        System.out.println("Arrays.asList(int[]) size = " + trap.size());
        System.out.println("its first element length = "
                + trap.get(0).length);

        Integer[] wrappers = {2, 4, 6};
        List<Integer> fixed = Arrays.asList(wrappers);
        fixed.set(0, 10);
        System.out.println("Integer[] after set = "
                + Arrays.toString(wrappers));
        try {
            fixed.add(8);
        } catch (UnsupportedOperationException ex) {
            System.out.println("Arrays.asList fixed size");
        }

        List<Integer> nullable = new ArrayList<>();
        nullable.add(null);
        try {
            int n = nullable.get(0); // Unboxing null.
            System.out.println(n);
        } catch (NullPointerException ex) {
            System.out.println("null unboxing: NullPointerException");
        }

        int[] defaultInts = new int[1];
        Integer[] defaultWrappers = new Integer[1];
        System.out.println("default int = " + defaultInts[0]);
        System.out.println("default Integer = " + defaultWrappers[0]);

        List<Integer> remove = new ArrayList<>(List.of(10, 20, 30));
        remove.remove(1);
        System.out.println("remove index 1 = " + remove);
        remove.remove(Integer.valueOf(30));
        System.out.println("remove value 30 = " + remove);
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 ListVsArrayDemo.java
java ListVsArrayDemo
```

Kết quả stdout:

```text
array length = 3
list size = 3
array first = 2, list first = 9
list after add = [9, 4, 6, 8]
unpacked = [9, 4, 6, 8]
stream boxed = [2, 4, 6]
toList is unmodifiable
Arrays.asList(int[]) size = 1
its first element length = 3
Integer[] after set = [10, 4, 6]
Arrays.asList fixed size
null unboxing: NullPointerException
default int = 0
default Integer = null
remove index 1 = [10, 30]
remove value 30 = [10]
```

**Giải thích:** việc gọi `set/add` trên `boxed` không sửa `raw` vì đó là hai vùng chứa độc lập. `Arrays.asList(raw)` cho `List<int[]>` có size 1. `Arrays.asList(wrappers)` cho danh sách cố định kích thước liên kết với mảng `Integer[]`. `Stream.toList` trả danh sách không sửa đổi được; unbox một `null` gây NPE; overload `remove(int)` và `remove(Object)` thực hiện hai thao tác khác nhau.

## 13. Nên chọn `int[]` hay `List<Integer>`?

| Nhu cầu | Lựa chọn ưu tiên | Lý do |
| --- | --- | --- |
| Dãy số nguyên kích thước cố định, xử lý số lượng lớn | `int[]` | Lưu primitive trực tiếp, thường có locality tốt và ít overhead |
| API Java yêu cầu `List<Integer>` | `List<Integer>` | Tương thích với Collection/Stream/thuật toán generic |
| Thêm/xóa linh hoạt | `ArrayList<Integer>` | Có khả năng resize; chú ý boxing/memory |
| Chỉ cần danh sách hằng ít phần tử | `List.of(1,2,3)` | Dễ đọc, không sửa đổi được, không cho `null` |
| Cần liên kết với một `Integer[]` có sẵn mà không đổi size | `Arrays.asList(integerArray)` | Backed by array; `set` hai chiều |
| Cần một `int[]` từ List để gọi API primitive | `mapToInt(Integer::intValue).toArray()` | Chuyển cấu trúc và unbox rõ ràng |
| Cần List từ mảng primitive | `Arrays.stream(arr).boxed()` hoặc vòng lặp | Boxing từng phần tử; chọn mutability rõ |
| Cần nhận biết “không có giá trị” bằng `null` | `List<Integer>`/`Integer[]` nếu hợp đồng cho phép | Không unbox trước khi xử lý `null` |
| Không được có `null` và dữ liệu luôn là số nguyên | `int[]` hoặc validation cho List | Loại nguy cơ null element |
| Yêu cầu độ chính xác từng số và hiệu năng cao | `int[]`/`long[]` tùy miền | Không dùng số thực hoặc wrapper nếu không cần |
| Collection cần equality/tra cứu/xóa phần tử linh hoạt | `List<Integer>` | Có API tiện dụng; phải hiểu `remove` và equality |

### Checklist trước khi chuyển qua lại

1. **Loại phần tử thực sự là gì?** `int`, `Integer`, `int[]` hay `Integer[]`? Đừng để `Arrays.asList` suy ra sai kiểu.
2. **Có cần thay đổi số phần tử không?** `int[]` cố định; `ArrayList` resize; `List.of` và `Stream.toList` không sửa đổi.
3. **Có cho phép `null` không?** Nếu có, chọn chính sách trước khi unbox; nếu không, validate hoặc chọn primitive.
4. **Có cần đồng bộ mảng và list không?** `Arrays.asList(Integer[])` backed by array; stream boxing tạo vùng chứa độc lập.
5. **Đã chọn API theo kiểu container chưa?** Mảng dùng `length`/`[]`; list dùng `size()`/`get`/`set`.
6. **Có rủi ro mất hiệu năng/bộ nhớ do boxing không?** Đo trên dữ liệu thật, cân nhắc `int[]` và `IntStream`.
7. **Khi so sánh/xóa, đang so nội dung hay tham chiếu/index?** `Arrays.equals` khác `List.equals`, `remove(int)` khác `remove(Object)`.
8. **Tổng số nguyên có thể vượt `int` không?** `IntStream.sum()` vẫn cho `int`; dùng `long`/chính sách checked theo nhu cầu.
9. **Có phụ thuộc implementation List không?** `get(i)` của `LinkedList` có tính chất khác `ArrayList`; đừng giả định mọi List đều random-access nhanh.
10. **Có yêu cầu tương thích Java cụ thể không?** `Stream.toList` từ Java 16; ví dụ chính biên dịch ở Java 17+.

## 14. Những lỗi hay gặp

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Viết `List<int>` | Không biên dịch | `List<Integer>` |
| Coi `int[]` là `List<Integer>` và cast | Không tương thích kiểu | Chuyển bằng vòng lặp/stream boxing |
| `Arrays.asList(new int[]{1,2,3})` rồi kỳ vọng list có ba số | Thực tế `List<int[]>` size 1 | `Arrays.stream(raw).boxed().toList()` |
| Cho rằng `Arrays.asList(Integer[])` đổi size được | `add/remove` ném exception | Sao chép vào `new ArrayList<>(...)` |
| Cho rằng `Stream.toList()` cho `ArrayList` mutable | Danh sách trả về unmodifiable | Bọc bằng `new ArrayList<>(...)` |
| Gọi `list.get(i)` mà không xét `null` | Unboxing có thể ném NPE | Kiểm tra null/validation |
| Tưởng `new ArrayList<>(capacity)` có sẵn `capacity` phần tử | `size()` vẫn 0 | Dùng `add` để điền |
| Dùng `list.remove(1)` để xóa giá trị số 1 | Java xóa index 1 | `remove(Integer.valueOf(1))` |
| Dùng `Integer == Integer` để so số | Có thể so identity wrapper, kết quả phụ thuộc object | `equals`/`Objects.equals` hoặc unbox có chủ đích |
| Dùng `array1.equals(array2)` để so nội dung | So identity mảng | `Arrays.equals(array1,array2)` |
| Giả định List phải có lưu trữ liên tục | `LinkedList` và implementation khác | Chọn implementation phù hợp |
| Lấy `List.toArray(new Integer[0])` làm `int[]` | Trả `Integer[]` | `mapToInt(...).toArray()` |
| Quên `IntStream.sum()` vẫn là `int` | Có thể overflow | `asLongStream().sum()` và kiểm tra miền |
| Chỉ đo benchmark bằng một lần chạy | Warmup/GC/JIT làm sai kết luận | Benchmark có kiểm soát như JMH |
| Coi nullable `Integer` bằng giá trị 0 | Mất khác biệt “thiếu” và 0 | Thiết kế dữ liệu rõ ràng |

## 15. Câu hỏi tự kiểm tra

1. `List<Integer>` có lưu trực tiếp các ô `int` 32 bit như `int[]` không? Vì sao?
2. Tại sao `List<int>` không biên dịch nhưng `List<Integer>` hợp lệ?
3. Viết ba cách đọc phần tử thứ hai từ `int[]`, `Integer[]` và `List<Integer>`.
4. Vì sao `Arrays.asList(intArray)` có size 1? Kiểu phần tử của list đó là gì?
5. `Arrays.asList(integerArray)` cho loại list nào? Vì sao `set` hợp lệ nhưng `add` không?
6. Nếu dùng `Arrays.stream(raw).boxed().toList()` rồi gọi `set`, điều gì xảy ra trên Java 17?
7. Có thể có `null` trong `int[]` không? Còn trong `ArrayList<Integer>`? Khi nào unboxing gây NPE?
8. Vì sao `new ArrayList<Integer>(100)` có `size() == 0`?
9. `List<Integer>.remove(1)` khác `remove(Integer.valueOf(1))` ở điểm nào?
10. Vì sao `Integer.valueOf(1000) == Integer.valueOf(1000)` không phải cách đáng tin để so giá trị?
11. Làm sao chuyển `List<Integer>` thành `int[]` mà không giữ các wrapper?
12. `Arrays.equals(int[],int[])` giải quyết bài toán gì mà `intArray.equals(otherIntArray)` không giải quyết?
13. Khi nào nên chọn `int[]` thay vì `ArrayList<Integer>` cho hàng triệu phần tử?
14. Nếu có `List<? extends Number>`, bạn có thể thêm mọi `Number` vào đó không? Vì sao?
15. Vì sao dùng `List<Integer>` không bảo đảm có thể gọi `get(i)` trong O(1)?

## 16. Tài liệu chính thức

- [Java SE 17 — `List<E>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): hợp đồng `get`, `set`, `add`, `remove`, `equals` và khả năng không hỗ trợ sửa đổi.
- [Java SE 17 — `ArrayList<E>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html): danh sách có thể resize và cơ chế truy cập.
- [Java SE 17 — `Arrays.asList`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)): danh sách kích thước cố định backed by array.
- [Java SE 17 — `Arrays.stream(int[])`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#stream(int[])): tạo `IntStream` từ mảng primitive.
- [Java SE 17 — `IntStream.boxed()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html#boxed()): boxing stream nguyên thủy sang `Stream<Integer>`.
- [Java SE 17 — `Stream.toList()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()): danh sách không sửa đổi được trả về từ stream.
- [Java Language Specification `5.1.7–5.1.8](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html): boxing và unboxing conversions trong Java.

**Kết luận:** `int[]` chứa trực tiếp các giá trị nguyên thủy có độ dài cố định; `List<Integer>` chứa các **tham chiếu `Integer`** với hành vi cấu trúc phụ thuộc implementation. Hai kiểu **không hoán đổi tự động** và cần boxing/unboxing khi chuyển đổi. Hãy chọn dựa trên nhu cầu API, thay đổi kích thước, `null`, hiệu năng và kiểu dữ liệu; đặc biệt tránh bẫy `Arrays.asList(int[])`, `remove` overload và các danh sách unmodifiable.