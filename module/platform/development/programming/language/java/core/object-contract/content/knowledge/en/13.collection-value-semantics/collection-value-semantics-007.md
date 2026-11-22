# Phần tử mảng trong Collection vẫn dùng quan hệ bằng nhau của mảng

## 1. Điều gì xảy ra khi đưa mảng vào Collection?

Trong Java, `List`, `Set` và `Map` thường sử dụng các phương thức `equals()` hoặc `hashCode()` của đối tượng phần tử hay khóa để quyết định hai giá trị có tương đương hay không. **Collection không tự đổi quy tắc so sánh của phần tử mảng thành so sánh từng phần tử bên trong mảng.**

Xét hai mảng độc lập:

```java
int[] a = {1, 2, 3};
int[] b = {1, 2, 3};

System.out.println(a == b);             // false
System.out.println(a.equals(b));        // false
System.out.println(Arrays.equals(a, b)); // true
```

*Đây là đoạn lệnh minh họa đặt bên trong phương thức có `import java.util.Arrays;`. Chương trình đầy đủ ở mục 6.*

Mặc dù `a` và `b` chứa các số nguyên giống nhau theo cùng thứ tự, chúng là **hai đối tượng mảng khác nhau**. Mảng Java **không ghi đè `Object.equals()` để so nội dung**. Do đó:

- `a == b` là `false` vì khác tham chiếu.
- `a.equals(b)` cũng `false` vì kế thừa so sánh tham chiếu từ `Object`.
- `Arrays.equals(a, b)` là `true` vì phương thức tiện ích này **chủ động so từng phần tử tương ứng**.

Đây chính là điểm dễ nhầm: khi mảng trở thành phần tử của `Collection`, nó **vẫn là một object mảng với equality mặc định của mảng**, chứ không được Collection biến thành value object. Cùng dữ liệu không đồng nghĩa cùng phần tử theo `equals()` của mảng.

> **Quy tắc nhớ nhanh:** Collection dùng hợp đồng equality của phần tử. Phần tử là mảng Java thì equality mặc định là theo identity của mảng; muốn so nội dung phải chọn một cách biểu diễn hoặc thuật toán riêng.

## 2. Sự khác nhau giữa mảng và Collection có phần tử thông thường

Hai `List<Integer>` có các phần tử số giống nhau theo cùng thứ tự thường `equals()` nhau vì `Integer.equals()` so giá trị số:

```java
List<Integer> numbers1 = List.of(1, 2, 3);
List<Integer> numbers2 = List.of(1, 2, 3);

System.out.println(numbers1.equals(numbers2)); // true
```

Nhưng với **List chứa phần tử mảng**:

```java
int[] a = {1, 2, 3};
int[] b = {1, 2, 3};

List<int[]> list1 = List.of(a);
List<int[]> list2 = List.of(b);

System.out.println(list1.equals(list2)); // false
System.out.println(list1.contains(b));   // false
System.out.println(list1.contains(a));   // true
```

*Các đoạn code trên minh họa trong một phương thức với `import java.util.List;`.*

Lý do: hợp đồng `List.equals()` yêu cầu hai list có cùng số phần tử, và **cặp phần tử ở mỗi vị trí phải bằng nhau**. Khi phần tử là `int[]`, lời so sánh phần tử dùng `equals()` của mảng. `list1` có `a` còn `list2` có `b`, nên khác nhau dù `Arrays.equals(a, b)` là `true`.

`List.contains(o)` cũng sử dụng quan hệ equality để tìm phần tử. Một object mảng mới có cùng nội dung không tự được nhận diện là phần tử cũ. Ngược lại, cùng tham chiếu `a` thì được nhận diện.

| Biểu thức | Ý nghĩa | Với hai mảng `a` và `b` độc lập nhưng cùng nội dung |
| --- | --- | --- |
| `a == b` | Cùng tham chiếu? | `false` |
| `a.equals(b)` | Equality mặc định của mảng? | `false` |
| `Arrays.equals(a, b)` | Nội dung một chiều tương ứng bằng nhau? | `true` |
| `List.of(a).equals(List.of(b))` | List có phần tử bằng nhau theo `equals()`? | `false` |
| `List.of(a).contains(b)` | Có phần tử bằng `b` theo equality mặc định? | `false` |
| `List.of(a).contains(a)` | Có cùng đối tượng mảng `a`? | `true` |

Nên phân biệt **mảng là phần tử của Collection** với **dữ liệu đã được chuyển thành các phần tử giá trị của Collection**:

- `List<int[]>` chứa mảng như một đối tượng phần tử.
- `List<Integer>` chứa từng `Integer`; equality của mỗi `Integer` là theo giá trị.
- `List<List<Integer>>` so các list con theo `List.equals()`, nếu các phần tử bên trong có equality phù hợp.

Một Collection không có khái niệm mặc định “bóc mảng ở bất kỳ độ sâu nào rồi so các giá trị”.

## 3. Tác động lên List, Set và Map

### 3.1. List: equals, contains, indexOf, remove

Một `ArrayList<int[]>` hoặc `List<int[]>` sử dụng equality của mảng khi kiểm tra `contains()` hay tìm chỉ số bằng `indexOf()`. Nếu gọi `remove(Object)` bằng một mảng mới cùng nội dung, nó cũng không xóa mảng đã lưu, vì không tìm thấy phần tử bằng nhau theo quy tắc của mảng.

```java
List<int[]> rows = new ArrayList<>();
int[] oldRow = {10, 20};
rows.add(oldRow);

System.out.println(rows.contains(new int[]{10, 20})); // false
System.out.println(rows.indexOf(oldRow));               // 0
System.out.println(rows.remove(new int[]{10, 20}));     // false
```

*Đây là đoạn minh họa nằm trong phương thức với `import java.util.ArrayList;` và `import java.util.List;`. Phương thức `remove(Object)` của `List` trả về `boolean`, khác `remove(int index)`.*

### 3.2. HashSet: không tự loại mảng trùng nội dung

`HashSet` dựa trên `hashCode()/equals()` của phần tử. Các đối tượng mảng có `hashCode()` và `equals()` kế thừa từ `Object`, nên hai mảng khác tham chiếu sẽ được xem là **hai phần tử khác nhau**, kể cả khi mọi phần tử con bằng nhau.

```java
Set<int[]> set = new HashSet<>();
set.add(new int[]{1, 2});
set.add(new int[]{1, 2});

System.out.println(set.size()); // 2
```

Không được suy từ `Arrays.equals(first, second)` là `true` rằng `HashSet<int[]>` sẽ coi chúng là trùng nhau. Việc hai đối tượng có giá trị hash tình cờ giống nhau cũng không khiến chúng tự thành một phần tử: `HashSet` vẫn cần kiểm tra equality. Ngược lại, nếu thêm **chính instance mảng** hai lần, `HashSet` chỉ giữ một phần tử.

### 3.3. HashMap: mảng dùng làm khóa vẫn được so theo identity

Với `HashMap<int[], String>`, mảng khóa mới có cùng nội dung thường không tra được mapping được lưu bằng mảng khác:

```java
Map<int[], String> map = new HashMap<>();
int[] key = {1, 2};

map.put(key, "stored");

System.out.println(map.get(new int[]{1, 2})); // null
System.out.println(map.get(key));              // stored
```

*Đoạn minh họa dùng `java.util.Map` và `java.util.HashMap`.*

Điều này vẫn đúng về mặt hợp đồng `HashMap`: khóa mới không bằng khóa cũ theo `equals()` của mảng. Muốn map sử dụng **giá trị của mảng làm định danh**, cần gói dữ liệu mảng trong một kiểu khóa định nghĩa `equals()/hashCode()` theo nội dung, hoặc chuyển mảng thành một dạng key khác có semantics giá trị rõ ràng.

Còn nếu mảng là **giá trị** thay vì khóa, ví dụ `Map<String, int[]>`, việc `get("id")` được hay không dựa vào `String` làm khóa. Nhưng so sánh hai `Map<String, int[]>` bằng `Map.equals()` vẫn xét `equals()` của các **giá trị** tương ứng; hai mảng value khác tham chiếu nhưng cùng nội dung sẽ không tự được xem là bằng nhau.

## 4. Những phương thức Arrays nào thực sự so nội dung?

`java.util.Arrays` cung cấp các phép so sánh rõ ràng dành cho mảng:

| Phương thức | Tình huống áp dụng | Điểm cần nhớ |
| --- | --- | --- |
| `Arrays.equals(int[], int[])` và các overload primitive | So hai mảng nguyên thủy một chiều | So các phần tử cùng vị trí bằng quy tắc tương ứng với kiểu dữ liệu. |
| `Arrays.equals(Object[], Object[])` | So mảng đối tượng một chiều | So từng phần tử bằng equality tương ứng; phần tử **lại là mảng** thì mặc định vẫn so identity của mảng con. |
| `Arrays.deepEquals(Object[], Object[])` | So mảng đối tượng có cấu trúc lồng, gồm mảng con | Khi gặp mảng con, đi sâu theo nội dung; phù hợp với nhiều tình huống mảng đa chiều. |
| `Arrays.hashCode(array)` | Tính hash theo nội dung một chiều | Phải đi cùng `Arrays.equals(...)` thích hợp khi làm kiểu khóa giá trị. |
| `Arrays.deepHashCode(Object[])` | Hash theo nội dung mảng lồng | Đi cặp với `Arrays.deepEquals(...)` khi chọn chính sách equality sâu. |
| `Arrays.toString(array)` | In mảng một chiều dễ đọc | Chỉ là biểu diễn; không định nghĩa equality. |
| `Arrays.deepToString(Object[])` | In mảng lồng dễ đọc | Cũng chỉ dùng cho biểu diễn, không làm thay đổi equality. |

Ví dụ mảng hai chiều trong Java thực chất là **mảng các mảng**, nên:

```java
int[][] a = {{1, 2}, {3}};
int[][] b = {{1, 2}, {3}};

System.out.println(Arrays.equals(a, b));     // false
System.out.println(Arrays.deepEquals(a, b)); // true
```

Ở đây `Arrays.equals(a, b)` được chọn theo overload `Object[]` vì `int[][]` là mảng gồm các phần tử `int[]`. Hai phần tử `int[]` độc lập không bằng nhau theo `Object.equals()`. `Arrays.deepEquals(a, b)` nhận ra các mảng con và so nội dung nguyên thủy tương ứng.

Lưu ý sự khác nhau giữa các kiểu:

- `Arrays.equals(new int[]{1,2}, new int[]{1,2})` → `true`.
- `Arrays.equals(new int[][]{{1}}, new int[][]{{1}})` → `false` vì so hai mảng con theo tham chiếu.
- `Arrays.deepEquals(new int[][]{{1}}, new int[][]{{1}})` → `true`.

Nếu chỉ cần xử lý mảng nguyên thủy một chiều, `Arrays.equals()` là lựa chọn trực tiếp và dễ hiểu. Với mảng lồng, dùng `deepEquals` khi ngữ nghĩa nghiệp vụ thật sự cần so đến nội dung các cấp. Các phương thức `Arrays.equals` không biến mảng thành object có `equals()` theo nội dung cho những nơi khác sử dụng.

## 5. Vì sao việc bọc bằng List.of, Arrays.asList hay List.copyOf chưa đủ?

Một sai lầm thường gặp là cho rằng chỉ cần đặt mảng vào một list bất biến thì equality của mảng sẽ trở thành equality theo nội dung. Trên thực tế:

```java
int[] a = {1, 2};
int[] b = {1, 2};

List<int[]> first = List.of(a);
List<int[]> second = List.of(b);

System.out.println(first.equals(second)); // false
```

`List.of(...)` tạo list không sửa được cấu trúc, **không sao chép sâu phần tử mảng** và không ghi đè phương thức của `int[]`. Nếu đổi `a[0]`, nội dung array đang chứa trong `first` cũng đổi. Tương tự, `List.copyOf(...)` tạo list không sửa được cấu trúc với các phần tử của nguồn, nhưng vẫn có thể chứa các object mutable.

`Arrays.asList(...)` cũng dễ gây nhầm lẫn với mảng primitive. Đặc biệt:

```java
List<int[]> oneElement = Arrays.asList(new int[]{1, 2, 3});
System.out.println(oneElement.size()); // 1
```

Đây là một list **có một phần tử kiểu `int[]`**, không phải `List<Integer>` có ba phần tử. Primitive `int[]` không tự tách và boxing thành ba `Integer` cho lời gọi varargs này.

Đối với mảng tham chiếu `String[]`, `Arrays.asList(stringArray)` thường tạo danh sách các phần tử `String` vì `String[]` khớp trực tiếp tham số varargs `T...`. Hai trường hợp rất khác nhau nên cần kiểm tra kiểu generic và ý nghĩa chính xác của dữ liệu.

Nếu muốn một `List<Integer>` từ `int[]`, có thể chủ động boxing:

```java
int[] source = {1, 2, 3};
List<Integer> values = Arrays.stream(source)
        .boxed()
        .toList();

System.out.println(values.equals(List.of(1, 2, 3))); // true
```

Trong Java 17+, `Stream.toList()` tạo list không sửa được cấu trúc. Các phần tử lúc này là `Integer`, nên equality của phần tử xét giá trị. Cách chuyển đổi này thay đổi mô hình dữ liệu và có chi phí boxing; chỉ nên dùng khi thật sự cần list các số nguyên theo giá trị.

## 6. Chương trình Java 17+ hoàn chỉnh, có thể tự chạy

Chương trình minh họa một chuỗi hành vi cụ thể: array identity, `List.contains()`, `HashSet`, `HashMap`, so mảng lồng, sự khác biệt của `Arrays.asList` và một **wrapper so nội dung**.

Tạo tệp `ArrayCollectionEqualityDemo.java`:

```java
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class ArrayCollectionEqualityDemo {

    // Value wrapper: bảo vệ snapshot và định nghĩa equality theo nội dung.
    record IntArrayKey(int[] values) {
        IntArrayKey {
            Objects.requireNonNull(values, "values");
            values = Arrays.copyOf(values, values.length);
        }

        @Override
        public int[] values() {
            return Arrays.copyOf(values, values.length);
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof IntArrayKey that
                    && Arrays.equals(values, that.values);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(values);
        }
    }

    public static void main(String[] args) {
        int[] a = {1, 2, 3};
        int[] b = {1, 2, 3};

        System.out.println(a == b);
        System.out.println(a.equals(b));
        System.out.println(Arrays.equals(a, b));

        List<int[]> listA = List.of(a);
        List<int[]> listB = List.of(b);
        System.out.println(listA.equals(listB));
        System.out.println(listA.contains(b));
        System.out.println(listA.contains(a));

        Set<int[]> rawSet = new HashSet<>();
        rawSet.add(a);
        rawSet.add(b);
        System.out.println(rawSet.size());
        System.out.println(rawSet.contains(new int[]{1, 2, 3}));

        Map<int[], String> rawMap = new HashMap<>();
        rawMap.put(a, "stored");
        System.out.println(rawMap.get(b));
        System.out.println(rawMap.get(a));

        int[][] nested1 = {{1, 2}, {3}};
        int[][] nested2 = {{1, 2}, {3}};
        System.out.println(Arrays.equals(nested1, nested2));
        System.out.println(Arrays.deepEquals(nested1, nested2));

        System.out.println(
                List.of(1, 2, 3).equals(List.of(1, 2, 3)));
        System.out.println(Arrays.asList(new int[]{1, 2, 3}).size());

        List<IntArrayKey> valueList = List.of(new IntArrayKey(a));
        System.out.println(valueList.contains(new IntArrayKey(b)));

        Set<IntArrayKey> valueSet = new HashSet<>();
        valueSet.add(new IntArrayKey(a));
        valueSet.add(new IntArrayKey(b));
        System.out.println(valueSet.size());

        Map<IntArrayKey, String> valueMap = new HashMap<>();
        valueMap.put(new IntArrayKey(a), "number-sequence");
        System.out.println(valueMap.get(new IntArrayKey(b)));

        int[] source = {5, 6};
        IntArrayKey snapshot = new IntArrayKey(source);
        source[0] = 9;               // Sửa input sau constructor.
        int[] exported = snapshot.values();
        exported[0] = 10;            // Sửa array trả ra từ accessor.
        System.out.println(Arrays.toString(snapshot.values()));
    }
}
```

Biên dịch và chạy:

```bash
javac ArrayCollectionEqualityDemo.java
java ArrayCollectionEqualityDemo
```

Stdout theo đúng thứ tự:

```text
false
false
true
false
false
true
2
false
null
stored
false
true
true
1
true
1
number-sequence
[5, 6]
```

Giải thích kết quả:

1. Ba dòng đầu lần lượt cho biết hai instance mảng khác nhau, `Object.equals()` của array vẫn so tham chiếu, nhưng `Arrays.equals` so nội dung là `true`.
2. `listA.equals(listB)` và `listA.contains(b)` đều `false` vì phần tử mảng `a` và `b` không `equals()` nhau. `listA.contains(a)` là `true` vì đây là cùng đối tượng.
3. `rawSet.size() == 2`: cùng nội dung không bị loại trùng khi phần tử là hai đối tượng array khác nhau. Tìm bằng mảng mới tiếp tục thất bại.
4. `rawMap.get(b)` là `null` còn `rawMap.get(a)` là `stored`: làm khóa `HashMap` bằng array mặc định là chọn **identity của array**, không chọn nội dung.
5. Với hai mảng hai chiều, `Arrays.equals` cho `false` vì mảng con khác tham chiếu; `Arrays.deepEquals` cho `true` vì nội dung lồng giống nhau.
6. Hai `List<Integer>` cùng dãy giá trị bằng nhau; `Arrays.asList(new int[]{...})` lại chỉ có một phần tử `int[]`.
7. `valueList.contains(new IntArrayKey(b))` là `true`: wrapper cung cấp equality theo nội dung. `valueSet.size()` là `1` vì hai wrapper có cùng nội dung khóa. Tra cứu `valueMap` bằng wrapper tạo mới thành công.
8. `snapshot` vẫn in `[5, 6]` dù mảng đầu vào đã bị sửa và accessor trả ra mảng đã bị sửa: wrapper chủ động **copy phòng vệ** ở cả lúc nhận và lúc trả dữ liệu.

Kết quả không phụ thuộc vào giá trị số cụ thể của `Object.hashCode()`, vì chương trình không in identity hash hay thứ tự duyệt `HashSet`.

## 7. Tạo value wrapper đúng cách: equals, hashCode và bất biến

Khi thật sự cần mảng **là một khóa giá trị**, lớp bọc thường rõ ràng hơn cố dùng trực tiếp `int[]`. `IntArrayKey` trong chương trình có ba trách nhiệm:

**(1) Equality theo nội dung:** `Arrays.equals(values, that.values)` quyết định hai khóa có cùng dãy số và thứ tự hay không.

**(2) Hash tương thích:** `Arrays.hashCode(values)` phản ánh nội dung đúng theo `Arrays.equals(...)`. Nếu hai wrapper bằng nhau, chúng có cùng hash. Không được chỉ ghi đè `equals()` rồi giữ hash mặc định của `Object`.

**(3) Snapshot ổn định:** constructor `Arrays.copyOf(...)` để ngăn code ngoài sửa array đã giao, và accessor cũng trả bản sao. Nếu chỉ có `private final int[] values` nhưng lưu trực tiếp array đầu vào, code ngoài vẫn có thể thay các phần tử. Khi làm khóa `HashMap` hoặc phần tử `HashSet`, nội dung mutable làm hash thay đổi có thể khiến thao tác tra cứu hoạt động sai.

Một `record` thông thường như:

```java
record BadArrayKey(int[] values) {}
```

**không tự có equality theo nội dung mảng**. Record mặc định tính equality theo các component, nhưng component là mảng vẫn được so theo equality của array; `new BadArrayKey(new int[]{1,2})` và một `BadArrayKey` khác chứa mảng `{1,2}` riêng biệt không tự bằng nhau. `record` cũng không tự sao chép sâu các object tham chiếu. Nếu dùng record làm wrapper, cần ghi đè `equals()/hashCode()` tương thích và bảo vệ dữ liệu mutable như ví dụ đầy đủ.

### Mảng đối tượng, mảng lồng và wrapper tổng quát

Nếu mảng chứa `String` hoặc value object có `equals()` thích hợp, dùng `Arrays.equals(Object[], Object[])` có thể đủ vì nó so từng phần tử bằng nhau theo equality của phần tử.

Nếu mỗi phần tử lại là mảng, `Arrays.equals(Object[], Object[])` có thể vẫn so identity của mảng con. Khi bài toán cần so toàn bộ cấu trúc lồng, cân nhắc `Arrays.deepEquals` và `Arrays.deepHashCode` theo cặp. Cần xác định trước xem thứ tự và phân biệt `null` ở các cấp có quan trọng không; `deepEquals` không phải chính sách chuẩn cho mọi đồ thị đối tượng tùy ý.

Nếu phần tử mảng là đối tượng mutable khác, dù wrapper đã `Arrays.copyOf` lớp mảng bên ngoài, **các phần tử tham chiếu bên trong vẫn được chia sẻ**. Muốn snapshot thực sự ổn định, phải áp dụng copy phòng vệ hoặc thiết kế bất biến cho các phần tử có ảnh hưởng equality/hash. Không có cơ chế tự sao chép sâu mọi object graph trong Java.

## 8. Khi nào có thể dùng array identity, khi nào cần so theo giá trị?

Không phải dùng mảng làm phần tử hay khóa Collection luôn sai. Quyết định phụ thuộc vào nghĩa của dữ liệu:

| Nhu cầu | Hướng xử lý |
| --- | --- |
| Theo dõi **chính instance mảng** như một buffer/tài nguyên riêng | Giữ tham chiếu mảng trực tiếp có thể phù hợp, vì identity là điều mong muốn. |
| Chỉ cần in hoặc so sánh hai mảng độc lập một lần | Dùng `Arrays.toString` hoặc `Arrays.equals`/`Arrays.deepEquals` trực tiếp, không cần wrapper. |
| `List` chứa các dãy số và muốn `contains` nhận dãy khác instance nhưng cùng nội dung | Dùng value wrapper hoặc biểu diễn bằng `List<Integer>` nếu mô hình và chi phí boxing phù hợp. |
| `HashSet` phải loại các mảng có cùng nội dung | Bọc bằng kiểu có equality/hash theo nội dung và snapshot ổn định. |
| `HashMap` dùng mảng làm khóa logic | Dùng wrapper bất biến với `equals()` và `hashCode()` tương ứng, hoặc encode khóa bằng một value type thích hợp. |
| Cấu trúc mảng nhiều cấp cần so sâu | Dùng `Arrays.deepEquals/deepHashCode` theo cặp khi phù hợp với semantics cần thiết. |

Một cách chuyển `int[]` thành `List<Integer>` trong Java 17+ là:

```java
int[] input = {1, 2, 3};

List<Integer> values = Arrays.stream(input)
        .boxed()
        .toList();

System.out.println(values.equals(List.of(1, 2, 3))); // true
```

*Đoạn minh họa nằm trong phương thức đã import `Arrays` và `List`.* Đây là **chuyển đổi mô hình từ mảng nguyên thủy thành list phần tử boxed**, không phải thay đổi equality của `int[]`. Có chi phí boxing và bộ nhớ cho collection, nên cân nhắc theo mục đích. Nếu cần xử lý một dãy primitive mà không cần Collection semantics, tiếp tục dùng array và `Arrays.equals` có thể đơn giản hơn.

## 9. Các lỗi thường gặp

**Lỗi 1 — Nghĩ `Collection.equals()` tự so sâu tất cả kiểu phần tử.** Equality của Collection thường đi qua equality của từng phần tử. Phần tử mảng khác instance thì `equals()` mặc định không so nội dung.

**Lỗi 2 — Dùng `array.toString()` để tạo khóa.** Mảng thường có chuỗi biểu diễn kiểu/tên lớp và hash, không mô tả nội dung như `Arrays.toString(array)`. Dù dùng `Arrays.toString` để in, không nên tự động coi chuỗi mô tả là kiểu khóa thay vì value type có hợp đồng rõ ràng.

**Lỗi 3 — Dùng `Arrays.equals` cho mảng đa chiều rồi cho rằng đã so sâu.** Với `int[][]`, phần tử bên ngoài là `int[]` nên `Arrays.equals` chỉ so equality mặc định của mảng con. Nếu muốn so từng giá trị lồng, dùng `Arrays.deepEquals`.

**Lỗi 4 — Bọc array trong `record` rồi nghĩ equality đã theo nội dung.** Record equality vẫn dùng semantics của từng component, mà array component là kiểu tham chiếu với equality theo identity. Muốn nội dung, ghi đè đúng `equals()/hashCode()`.

**Lỗi 5 — Quên hashCode của wrapper.** `HashSet`, `HashMap` dựa vào cả `hashCode` và `equals`. Wrapper có content equality nhưng identity hash có thể phá contract và làm lookup thất bại.

**Lỗi 6 — Chỉ đánh dấu trường array là `final`.** `final` ngăn gán một mảng khác vào trường nhưng không ngăn `values[0] = ...`. Nếu nội dung tham gia hash, phải bảo vệ snapshot.

**Lỗi 7 — Nhầm `Arrays.asList(int[])` thành `List<Integer>`.** Nó tạo một list có một phần tử `int[]`. Muốn từng số nguyên như phần tử Collection, cần boxing/chuyển đổi tường minh.

**Lỗi 8 — Đồng nhất mọi dạng Map theo `equals()`.** `IdentityHashMap` dùng identity một cách chủ đích; `TreeMap` chọn tương đương khóa theo `Comparator`/`Comparable`; bài này nói về các collection/map thông thường sử dụng hợp đồng equality của phần tử/khóa, đặc biệt `List`, `HashSet`, `HashMap`.

## 10. Tự kiểm tra

**Câu 1.** Hai mảng `int[]` riêng biệt cùng chứa `{4,5}` có bằng nhau theo `Object.equals()` không?  
**Đáp án:** Không. Mảng dùng reference equality mặc định; `Arrays.equals` mới so nội dung một chiều.

**Câu 2.** `new HashSet<int[]>()` thêm hai mảng mới cùng dữ liệu có thể có `size() == 1` vì nội dung trùng không?  
**Đáp án:** Không. Khi cả hai là instance riêng, Set coi là hai phần tử khác nhau; `size() == 2`.

**Câu 3.** `List.of(new int[]{1}).equals(List.of(new int[]{1}))` cho kết quả gì?  
**Đáp án:** `false`, vì mỗi list có một phần tử là mảng khác tham chiếu.

**Câu 4.** `Arrays.deepEquals` và `Arrays.equals` khác nhau như thế nào với `int[][]`?  
**Đáp án:** `Arrays.equals` so mỗi mảng con theo equality mặc định của mảng, còn `deepEquals` so tiếp nội dung các mảng con.

**Câu 5.** Một record có component `int[]` được Java tự sinh equality theo nội dung array chưa?  
**Đáp án:** Chưa. Cần định nghĩa equality/hash theo `Arrays.equals/Arrays.hashCode` và bảo vệ tính bất biến nếu dùng làm khóa.

**Câu 6.** Muốn tra cứu `HashMap` bằng một array khác instance nhưng cùng nội dung thì nên làm gì?  
**Đáp án:** Dùng value wrapper bất biến có `equals()` và `hashCode()` theo nội dung, hoặc chuyển biểu diễn khóa thành value type phù hợp; đừng dùng `int[]` trực tiếp nếu cần content equality.

**Câu 7.** Vì sao wrapper phải copy mảng ở constructor và accessor khi nội dung dùng làm khóa?  
**Đáp án:** Để bên ngoài không thể thay giá trị tham gia equality/hash trong thời gian object nằm trong collection băm.

Điểm cần nhớ: **Collection tuân theo hợp đồng equality của đối tượng phần tử. Mảng Java tự thân dùng identity equality; `Arrays.equals/deepEquals` chỉ so nội dung khi bạn gọi rõ ràng.** Nếu nghiệp vụ cần các mảng khác instance nhưng cùng nội dung được xem là cùng giá trị trong `List`, `Set` hoặc `Map`, hãy biểu diễn chúng bằng một kiểu khóa hoặc phần tử có content equality và hash tương thích.