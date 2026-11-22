# Thay đổi mảng tại chỗ và xử lý lỗi trong Java

## 1. Mục tiêu bài học

**Thay đổi mảng tại chỗ (in-place array mutation)** nghĩa là sửa các phần tử bên trong **chính đối tượng mảng đã tồn tại**, thay vì tạo ra một mảng mới để trả về. Trong Java, mảng là đối tượng, có chiều dài cố định, lưu các phần tử primitive hoặc các tham chiếu object. Việc gán `array[index] = value`, gọi `Arrays.fill`, `Arrays.sort`, `Arrays.setAll` hay `System.arraycopy` vào một mảng đích là những thao tác có thể thay đổi mảng.

Bài học tập trung vào **cách sửa mảng an toàn và xử lý lỗi đúng**. Bạn sẽ hiểu:

1. Phân biệt **thay đổi nội dung**, **thay đổi biến tham chiếu** và **tạo bản sao**; nhận diện alias giữa các biến hoặc thành phần mảng nhiều chiều.
2. Dùng gán phần tử, `Arrays.fill`, `Arrays.setAll`, `Arrays.parallelSetAll`, `Arrays.sort` và `System.arraycopy` đúng với phạm vi và ý nghĩa của chúng.
3. Xử lý các ngoại lệ hiện hành: `ArrayIndexOutOfBoundsException`, `IndexOutOfBoundsException`, `ArrayStoreException`, `NullPointerException`, `NegativeArraySizeException`, `IllegalArgumentException` và `ArithmeticException` trong từng tình huống.
4. Hiểu rằng **một lỗi phát sinh giữa quá trình sửa mảng có thể để lại thay đổi một phần**. Không giả định mọi thao tác in-place có rollback tự động.
5. Khi cần “hoặc cập nhật hết, hoặc giữ nguyên”, thiết kế theo hướng **kiểm tra trước**, **tính vào bản sao**, rồi **commit** trong điều kiện kiểm soát quyền truy cập.
6. Biết phạm vi của việc tránh data race: một mảng thông thường không tự có đồng bộ luồng, và “commit bằng copy” **không có nghĩa** được thực thi nguyên tử đối với các luồng khác.

Các API được giới thiệu vẫn áp dụng trong Java hiện đại. Chương trình runnable dùng **Java 17+**; `Objects.checkIndex` và các phương thức kiểm tra phạm vi được bổ sung sau Java 8, hiện vẫn được hỗ trợ. Những ví dụ cơ bản của `Arrays` và `System.arraycopy` có từ trước và vẫn dùng tốt.

## 2. Ba khái niệm không được nhầm

### 2.1. Thay đổi tại chỗ: đối tượng mảng giữ nguyên

```java
int[] values = {10, 20, 30};
values[1] = 99; // Cùng đối tượng mảng, nay là [10, 99, 30]
```

Mảng được tạo một lần, phần tử thứ hai được thay đổi. Không có mảng mới được tạo từ câu lệnh gán.

### 2.2. Alias: hai biến cùng trỏ đến một mảng

```java
int[] a = {1, 2, 3};
int[] b = a;

b[0] = 88;

System.out.println(Arrays.toString(a)); // [88, 2, 3]
System.out.println(a == b);              // true
```

Đây là **đoạn minh họa** trong phương thức đã import `java.util.Arrays`. Cả `a` và `b` trỏ đến cùng đối tượng; thay đổi qua `b` được quan sát qua `a`. Nếu API nhận mảng từ caller rồi sửa trực tiếp, caller cũng thấy thay đổi.

### 2.3. Copy và reassign: đối tượng khác, ý nghĩa khác

```java
int[] a = {1, 2, 3};
int[] copied = a.clone();
copied[0] = 88;

System.out.println(Arrays.toString(a));     // [1, 2, 3]
System.out.println(Arrays.toString(copied)); // [88, 2, 3]

a = new int[]{7, 8}; // Thay biến a trỏ sang đối tượng mảng khác.
```

`a = ...` **không** thay kích thước của mảng cũ. Nó chỉ cho biến tham chiếu `a` trỏ đến một đối tượng khác. Những alias còn trỏ đến mảng cũ sẽ không “đi theo” `a`.

**Lưu ý về `final`:**

```java
final int[] data = {1, 2};
data[0] = 10;           // Hợp lệ, sửa phần tử.
// data = new int[3];   // Không hợp lệ: không được gán lại biến final.
```

`final` đóng băng **tham chiếu của biến**, không làm các phần tử của mảng trở nên immutable. Một mảng Java thông thường vẫn là đối tượng có thể sửa.

## 3. Thay một phần tử: kiểm soát chỉ số và giá trị

Chỉ số hợp lệ của một mảng dài `n` là `0` đến `n - 1`. Khi `n == 0` thì **không có chỉ số hợp lệ**.

```java
int[] scores = {50, 60, 70};
scores[2] = 95; // [50, 60, 95]

// scores[3] = 100; // ArrayIndexOutOfBoundsException.
// scores[-1] = 0;  // ArrayIndexOutOfBoundsException.
```

Java kiểm tra bounds khi truy cập mảng. Không có cơ chế tự “mở rộng” mảng khi gán vào vị trí `length`: đó là lỗi. Nếu cần thêm/xóa phần tử linh hoạt, `ArrayList` hoặc một cấu trúc dữ liệu động thường phù hợp hơn.

### 3.1. Kiểm tra chỉ số và phạm vi

Với Java 9+ có các tiện ích `java.util.Objects`:

```java
int valid = Objects.checkIndex(2, scores.length);        // 2
int from = Objects.checkFromToIndex(1, 3, scores.length); // 1
int start = Objects.checkFromIndexSize(0, 2, scores.length); // 0
```

Đây là **đoạn minh họa** với `scores` đã khai báo. Những hàm này trả chỉ số bắt đầu khi hợp lệ và ném `IndexOutOfBoundsException` nếu không hợp lệ. Chúng hữu ích khi muốn **kiểm tra trước khi bắt đầu thay đổi**.

Quy tắc phạm vi **nửa mở**:

- `fromIndex` **bao gồm**.
- `toIndex` **không bao gồm**.
- Phạm vi `[fromIndex, toIndex)` có thể rỗng khi hai biên bằng nhau.
- Phải có `0 <= fromIndex <= toIndex <= array.length`.
- Với `checkFromIndexSize(from, size, length)`, phải có kích thước không âm và toàn bộ đoạn nằm trong array, tính cả nguy cơ overflow khi cộng chỉ số.

**Chọn hàm kiểm tra phù hợp với API định gọi.** Với `Arrays.fill(a, from, to, val)`, bạn có thể dùng `Objects.checkFromToIndex` trước khi tiến hành. Với `System.arraycopy`, kiểm tra riêng phạm vi nguồn/đích theo độ dài sao chép trước khi gọi.

### 3.2. Tránh sửa một phần do kiểm tra quá muộn

Ví dụ không nên:

```java
for (int i = 0; i < requestedCount; i++) {
    scores[i] += 10; // Có thể đã sửa nhiều phần tử trước khi i vượt biên.
}
```

Đây là **anti-pattern minh họa** với `requestedCount` giả định đến từ bên ngoài. Khi `requestedCount > scores.length`, các phần tử đầu bị tăng, rồi mới phát sinh `ArrayIndexOutOfBoundsException`.

Hướng tốt hơn:

```java
Objects.checkFromIndexSize(0, requestedCount, scores.length);
for (int i = 0; i < requestedCount; i++) {
    scores[i] = Math.addExact(scores[i], 10);
}
```

Đoạn này **tránh lỗi phạm vi xảy ra sau một số phần tử**, nhưng vẫn **không bảo đảm all-or-nothing nếu `Math.addExact` ném ngoại lệ ở phần tử sau**. Muốn bảo đảm giữ nguyên mảng khi phép biến đổi thất bại, phải dùng thiết kế staging ở mục 9.

## 4. `Arrays.fill`: ghi một giá trị vào toàn bộ mảng hoặc một đoạn

Các overload thông dụng:

```java
Arrays.fill(int[] a, int value);
Arrays.fill(int[] a, int fromIndex, int toIndex, int value);
Arrays.fill(Object[] a, Object value);
Arrays.fill(Object[] a, int fromIndex, int toIndex, Object value);
```

Đây là **chữ ký rút gọn của các overload**, không phải phương thức có thể khai báo bên ngoài class. `Arrays` còn có overload cho các primitive khác.

Ví dụ:

```java
int[] codes = {1, 2, 3, 4, 5};
Arrays.fill(codes, 1, 4, 0);
// [1, 0, 0, 0, 5]

Arrays.fill(codes, -1);
// [-1, -1, -1, -1, -1]
```

Chỉ các vị trí `1`, `2`, `3` bị thay trong lời gọi đầu tiên. Giá trị tại index `4` không thuộc `[1,4)`. Lời gọi thứ hai ghi đè **mọi vị trí**, bao gồm cả phần tử trước đó.

**Lưu ý về Object[]:** `Arrays.fill(objects, mutableObject)` gán **cùng một tham chiếu** vào nhiều ô, **không** tạo bản sao độc lập cho mỗi phần tử:

```java
StringBuilder[] builders = new StringBuilder[2];
StringBuilder shared = new StringBuilder("x");
Arrays.fill(builders, shared);

builders[0].append("!");
System.out.println(builders[1]); // x!
```

Đoạn này cho thấy alias giữa hai ô. Nếu cần mỗi ô giữ một đối tượng độc lập, dùng `Arrays.setAll` với generator tạo mới theo index.

Các lỗi thường gặp: mảng null → `NullPointerException`; phạm vi đảo ngược → `IllegalArgumentException`; phạm vi ngoài mảng → `ArrayIndexOutOfBoundsException`; gán đối tượng không tương thích với runtime component type của object array → `ArrayStoreException`.

## 5. `Arrays.setAll` và `parallelSetAll`: tính giá trị theo chỉ số

`Arrays.setAll` cho phép đặt mọi phần tử bằng kết quả của một hàm nhận **chỉ số**:

```java
int[] squares = new int[5];
Arrays.setAll(squares, i -> i * i);
// [0, 1, 4, 9, 16]
```

Một số overload hiện hành:

| Mảng | Kiểu generator |
| --- | --- |
| `int[]` | `IntUnaryOperator`, đầu vào `index`, đầu ra `int` |
| `long[]` | `IntToLongFunction` |
| `double[]` | `IntToDoubleFunction` |
| `T[]` | `IntFunction<? extends T>` |

**Tham số `i` là vị trí, không phải giá trị cũ**. Với mã `Arrays.setAll(values, i -> i + 1)`, các ô nhận `1,2,3,...` theo index, chứ không phải mỗi giá trị hiện tại được cộng một.

### 5.1. Tạo các đối tượng mới độc lập

```java
StringBuilder[] builders = new StringBuilder[3];
Arrays.setAll(builders, i -> new StringBuilder("item-" + i));

builders[0].append("!");
// Chỉ builders[0] đổi; các ô được cấp phát đối tượng riêng.
```

Đây là đoạn minh họa trong method; cần `import java.util.Arrays`. Generator được gọi cho từng vị trí và trả giá trị gán vào vị trí đó.

### 5.2. Khi generator ném exception

Theo tài liệu `Arrays.setAll`: khi generator ném exception, exception được chuyển cho caller và mảng có thể ở **trạng thái chưa xác định về những ô đã được ghi**. Không giả định rollback tự động, và không viết logic kiểm thử phụ thuộc rằng “chắc chắn chỉ có k ô đầu đã đổi”.

```java
int[] data = {9, 9, 9, 9};

try {
    Arrays.setAll(data, i -> {
        if (i == 2) {
            throw new IllegalStateException("Không tạo được giá trị index 2");
        }
        return i + 1;
    });
} catch (IllegalStateException ex) {
    // Có lỗi. KHÔNG được mặc định dữ liệu vẫn là [9, 9, 9, 9].
}
```

Đây là đoạn minh họa có nhánh lỗi cố ý. Nếu nghiệp vụ bắt buộc bảo vệ trạng thái cũ, hãy **tính ra mảng mới rồi commit sau khi toàn bộ phép tính thành công**.

### 5.3. `parallelSetAll` có nên dùng luôn không?

`Arrays.parallelSetAll` cũng thay đổi chính mảng, nhưng tính các chỉ số song song. Nó có thể giúp khi mỗi phần tử có phép tính đủ nặng và dữ liệu đủ lớn; với vài chục phần tử hoặc generator đơn giản, overhead có thể khiến chậm hơn.

**Điều kiện an toàn:** generator nên là hàm **không side effect**, chỉ phụ thuộc vào index hoặc dữ liệu đầu vào **ổn định, không bị thay đổi**, không dựa vào thứ tự gọi, không viết vào các ô khác của mảng và không dùng trạng thái dùng chung thiếu đồng bộ.

```java
int[] powers = new int[5];
Arrays.parallelSetAll(powers, i -> i * i);
// [0, 1, 4, 9, 16]
```

Khi generator của `parallelSetAll` ném lỗi, API không cam kết mảng được khôi phục; exception có thể được chuyển thành unchecked exception từ lời gọi. **Không dùng `parallelSetAll` nếu phải bảo đảm tính nguyên tử hoặc phụ thuộc vào thứ tự cập nhật.**

## 6. `System.arraycopy`: sao chép một đoạn vào mảng đích đã có

Chữ ký:

```java
System.arraycopy(Object src, int srcPos,
                 Object dest, int destPos, int length);
```

Khi `src` và `dest` là các mảng tương thích, hàm sao chép `length` phần tử từ `src[srcPos ...]` sang `dest[destPos ...]`. **Nó thay đổi mảng đích tại chỗ**, không cấp phát một mảng đích mới.

Ví dụ:

```java
int[] source = {10, 20, 30, 40};
int[] target = {0, 0, 0, 0, 0};

System.arraycopy(source, 1, target, 2, 2);
// target = [0, 0, 20, 30, 0]
// source giữ nguyên.
```

**Ngữ nghĩa vùng chồng lấn:** nếu source và target là **cùng một array**, `arraycopy` thực hiện theo ngữ nghĩa như thể đã chụp dữ liệu nguồn vào một vùng tạm trước khi sao chép, nên kết quả không bị phá bởi việc overwrite ngay trong đoạn cần đọc.

```java
int[] a = {1, 2, 3, 4, 5};
System.arraycopy(a, 0, a, 1, 4);
// [1, 1, 2, 3, 4]
```

Kết quả này là bảo đảm của `System.arraycopy`, không phải mẹo phụ thuộc JVM.

### 6.1. Kiểm tra chỉ số, độ dài và loại mảng

Các lỗi cần nhớ:

- `src` hoặc `dest` null → `NullPointerException`.
- `srcPos < 0`, `destPos < 0`, `length < 0`, hoặc đoạn vượt kích thước → `IndexOutOfBoundsException`.
- `src`/`dest` không phải mảng; trộn mảng primitive khác kiểu (`int[]` sang `long[]`); trộn mảng primitive với mảng tham chiếu → `ArrayStoreException`.
- Với reference array mà một phần tử nguồn không thể gán vào runtime component type của đích → `ArrayStoreException`.

`System.arraycopy` **không thực hiện ép rộng tự động giữa các mảng primitive**. Ví dụ `int[]` không thể copy thẳng sang `long[]` chỉ vì từng `int` có thể mở rộng thành `long`; cần vòng lặp chuyển từng phần tử hoặc API chuyển đổi rõ ràng.

### 6.2. Lỗi có thể xảy ra **sau khi một số ô đã copy**

Điểm rất quan trọng của hợp đồng `System.arraycopy`: khi cả hai là reference array và phần tử nguồn thứ `k` không tương thích với runtime component type của mảng đích, **các phần tử trước `k` đã được copy**, còn phần tử lỗi và những phần sau chưa thay đổi.

```java
Object[] mixed = {"copied", Integer.valueOf(42), "not copied"};
String[] destination = {"start", "stay", "end"};

try {
    System.arraycopy(mixed, 0, destination, 0, 3);
} catch (ArrayStoreException ex) {
    System.out.println(Arrays.toString(destination));
    // [copied, stay, end]
}
```

Đây là đoạn Java trong một method đã import `java.util.Arrays`. **Mảng đích đã thay đổi một phần** dù lời gọi ném `ArrayStoreException`. Nếu caller yêu cầu all-or-nothing, không thể chỉ `try/catch` rồi cho rằng dữ liệu cũ nguyên vẹn.

**Phân biệt:** với lỗi kiểm tra phạm vi hoặc khác kiểu mảng primitive, tài liệu nêu đích **không bị sửa**; nhưng lỗi không tương thích của **một phần tử trong reference-array copy** có thể để lại prefix đã sao chép.

## 7. `Arrays.sort` và `parallelSort` cũng thay đổi chính mảng

`Arrays.sort(a)` sắp thứ tự các phần tử **ngay trong mảng a**:

```java
int[] values = {7, 2, 9, 1};
Arrays.sort(values);
// values = [1, 2, 7, 9]
```

Sắp một đoạn:

```java
int[] a = {10, 9, 5, 8, 7};
Arrays.sort(a, 1, 4);
// [10, 5, 8, 9, 7], chỉ đoạn [1,4) được sắp.
```

Đối với object array, có thể dùng comparator:

```java
String[] labels = {"bbb", "a", "cc"};
Arrays.sort(labels, Comparator.comparingInt(String::length)
        .thenComparing(Comparator.naturalOrder()));
// [a, cc, bbb]
```

Đây là đoạn minh họa trong method; cần import `java.util.*`. Comparator cần đúng luật, ổn định trong thời gian sort và tương thích dữ liệu; `Arrays.sort(T[], Comparator)` bảo đảm **stable sort** đối với các phần tử so bằng nhau. Các overload primitive không sử dụng Comparator object.

**Xử lý lỗi:**

- Đoạn `fromIndex > toIndex` → `IllegalArgumentException`.
- Đoạn nằm ngoài bounds → `ArrayIndexOutOfBoundsException`.
- Natural ordering của object array yêu cầu phần tử có thể so sánh được; dữ liệu trộn kiểu không tương thích có thể ném `ClassCastException`.
- Comparator vi phạm hợp đồng có thể dẫn đến `IllegalArgumentException` trong một số đường thực thi; đừng trông cậy exception được ném ở mọi dữ liệu sai.
- Nếu code comparator hoặc API sorting thất bại, không nên suy diễn rằng mảng chắc chắn vẫn nguyên trạng, trừ khi một hợp đồng cụ thể bảo đảm.

`Arrays.parallelSort` cũng thay đổi chính mảng và có thể dùng tác vụ song song cùng vùng nhớ làm việc. Không mặc định “parallel luôn nhanh”; hiệu năng phụ thuộc số lượng phần tử, loại dữ liệu và chi phí xử lý.

### 7.1. `Stream.sorted` là thao tác khác

```java
int[] original = {3, 1, 2};
int[] sortedCopy = Arrays.stream(original).sorted().toArray();
// original vẫn là [3, 1, 2].
// sortedCopy là [1, 2, 3].
```

Một pipeline Stream mới tạo kết quả qua `toArray`, không sửa tự động nguồn ban đầu. Nếu mục tiêu là **in-place**, dùng `Arrays.sort(original)` thay vì trông chờ `Stream.sorted()` thay array nguồn.

## 8. `Arrays.copyOf`, `copyOfRange` và `clone()` không phải cập nhật tại chỗ

Các API trả mảng mới:

| API | Hành vi | Cảnh báo |
| --- | --- | --- |
| `a.clone()` | Bản sao mảng mới cùng số phần tử | Shallow nếu phần tử chứa tham chiếu |
| `Arrays.copyOf(a, n)` | Mảng mới dài `n`, cắt bớt hoặc đệm giá trị mặc định | Không đổi length của mảng cũ |
| `Arrays.copyOfRange(a, from, to)` | Mảng mới với đoạn `[from,to)` | `to` có thể vượt length và được đệm mặc định |
| `System.arraycopy(src,...,dest,...)` | Ghi vào mảng dest **đã tồn tại** | Có thể làm thay đổi một phần nếu lỗi phần tử tham chiếu |
| `Arrays.fill` / `Arrays.sort` / `Arrays.setAll` | Thay đổi mảng được truyền vào | Không tự tạo mảng kết quả độc lập |

Ví dụ:

```java
int[] data = {1, 2, 3};
int[] bigger = Arrays.copyOf(data, 5);          // [1, 2, 3, 0, 0]
int[] sub = Arrays.copyOfRange(data, 1, 5);     // [2, 3, 0, 0]
int[] copy = data.clone();                      // [1, 2, 3]
```

**Bẫy `copyOfRange`:** một số người cho rằng `to` lớn hơn length chắc chắn phải lỗi. Với `Arrays.copyOfRange`, `to` có thể vượt độ dài ban đầu và kết quả được **đệm số 0** cho primitive số hoặc `null` cho object. Tuy nhiên `from` vẫn phải hợp lệ, `from <= to`, và độ dài yêu cầu vẫn phải hợp lệ/khả thi.

**Phân biệt “array mới” với “deep copy”:** với `T[]`, `copyOf`/`clone` chỉ sao chép tham chiếu của từng phần tử, không clone các object bên trong.

### 8.1. Nếu phải thay đổi độ dài

Mảng Java có `length` cố định từ khi khởi tạo. Để có “mảng dài hơn”:

```java
int[] old = {1, 2};
int[] extended = Arrays.copyOf(old, 3); // [1, 2, 0]
extended[2] = 3;                        // [1, 2, 3]
```

Bản thân `old` không dài ra. Nếu một biến khác vẫn trỏ `old`, biến đó thấy mảng cũ. Nếu ứng dụng cần thêm/xóa thường xuyên, dùng collection thay vì lặp lại quá nhiều lần copy mảng.

## 9. Bảo đảm khi thất bại: validation, staging và commit

### 9.1. “Đã catch exception” không đồng nghĩa “đã rollback”

Giả sử:

```java
int[] amounts = {1, 2, 3};
for (int i = 0; i < amounts.length; i++) {
    amounts[i] = Math.multiplyExact(amounts[i], 1_000_000_000);
}
```

Với `int`, hai phần tử đầu biến thành 1.000.000.000 và 2.000.000.000, sau đó phần tử 3 gây `ArithmeticException` do overflow. **Mảng có thể đã thay đổi một phần trước khi exception được ném**. Câu lệnh `catch (ArithmeticException ex)` không tự khôi phục các giá trị trước đó.

**Các mức bảo đảm cần phân biệt:**

| Mức | Ý nghĩa |
| --- | --- |
| Không kiểm soát | Một phần tử có thể đổi trước khi lỗi, caller phải kiểm tra lại trạng thái |
| Kiểm tra trước | Hạn chế lỗi phạm vi/định dạng nhưng không xử lý được mọi lỗi giữa phép biến đổi |
| Staging trên bản sao | Nếu phép tính lỗi trước commit, mảng gốc giữ nguyên |
| Atomic đối với nhiều thread | Những thread khác chỉ quan sát toàn bộ trạng thái cũ **hoặc** mới; đòi hỏi thiết kế đồng bộ/phát hành snapshot riêng, không tự có từ `arraycopy` |

### 9.2. Thiết kế staging cho một mảng `int[]`

Một cách hữu ích khi caller sở hữu độc quyền mảng trong lúc cập nhật:

```java
static void updateAllOrKeep(int[] array, IntUnaryOperator transform) {
    Objects.requireNonNull(array);
    Objects.requireNonNull(transform);

    int[] staged = array.clone(); // Bản sao làm việc.

    for (int i = 0; i < staged.length; i++) {
        staged[i] = transform.applyAsInt(staged[i]);
    }

    // Chỉ commit sau khi TẤT CẢ phần tử tính xong.
    System.arraycopy(staged, 0, array, 0, array.length);
}
```

Đây là đoạn method có thể đưa vào class, cần import `java.util.Objects` và `java.util.function.IntUnaryOperator`. Trong điều kiện mảng gốc không bị tác động đồng thời, nếu `transform` ném exception thì đoạn `arraycopy` **chưa chạy**, nên mảng gốc được giữ nguyên.

Với mảng `int[]` cùng độ dài đã biết, bước commit không bị lỗi chuyển kiểu phần tử. Nhưng đây vẫn không phải **transaction đa luồng**: một thread đọc mảng đồng thời trong lúc `arraycopy` ghi có thể nhìn thấy trạng thái hỗn hợp. Muốn cung cấp snapshot đồng nhất cho reader, thiết kế theo bất biến + thay thế **tham chiếu snapshot** an toàn (ví dụ qua `volatile` hoặc `AtomicReference`) hoặc khóa phù hợp.

**Giới hạn khác:** hàm `transform` cần làm việc trên giá trị truyền vào và không tự sửa `array` hay dữ liệu bên ngoài. Nếu `transform` có side effect ngoài mảng gốc, staging không thể rollback những side effect đó.

### 9.3. Hai lựa chọn thay thế

- **Prevalidate toàn bộ dữ liệu:** thích hợp khi có thể chứng minh thao tác còn lại không lỗi sau bước kiểm tra, không tiêu tốn bản sao; vẫn phải hiểu ngoại lệ có thể xảy ra trong code khác.
- **Trả mảng mới thay vì sửa input:** viết `int[] result = ...` rồi trả `result`; caller chủ động quyết định thay tham chiếu của mình. Đây thường là thiết kế dễ lý luận hơn khi cần giữ input bất biến.

Không nhất thiết mọi phép `a[i] = x` đều cần staging. Chỉ áp dụng khi việc thay đổi một phần thật sự gây lỗi nghiệp vụ và chi phí copy hợp lý.

## 10. Object array, covariance và `ArrayStoreException`

Mảng tham chiếu trong Java có tính **covariance**: có thể gán `String[]` vào một biến `Object[]`:

```java
Object[] objects = new String[2];
objects[0] = "OK";

// Dòng này biên dịch được nhưng lỗi khi chạy:
// objects[1] = Integer.valueOf(42);
```

**Vì sao?** Kiểu compile-time của biến là `Object[]`, nhưng đối tượng mảng thật có runtime component type là `String`. Java kiểm tra giá trị gán tại runtime và ném `ArrayStoreException` nếu không hợp lệ.

Điều này khác với `List<String>` và `List<Object>`: generic collections thường không covariant theo cách tương tự. Đừng ép kiểu mảng hoặc dùng `Object[]` để bỏ qua kiểm tra kiểu rồi trông chờ mọi giá trị được lưu an toàn.

### 10.1. Mảng đa chiều là mảng của mảng

`int[][]` là một mảng có phần tử là `int[]`. Java cho phép dạng “răng cưa” (jagged), các hàng có độ dài khác nhau:

```java
int[][] grid = {{1, 2, 3}, {4}};
// grid.length == 2
// grid[0].length == 3
// grid[1].length == 1
```

Khi đọc hoặc sửa, đừng luôn dùng `grid[0].length` làm chiều rộng của mọi hàng. Mỗi row có thể là `null` hoặc độ dài riêng nếu dữ liệu cho phép, nên kiểm tra ở đúng cấp.

### 10.2. Shallow copy không bảo vệ các hàng bên trong

```java
int[][] grid = {{1, 2}, {3}};
int[][] outerOnly = grid.clone();

outerOnly[0][0] = 99;
System.out.println(grid[0][0]); // 99
```

`grid.clone()` chỉ sao chép mảng ngoài; `outerOnly[0]` và `grid[0]` vẫn trỏ tới **cùng mảng con**.

Nếu tất cả row đều không null và bạn cần bản sao từng row:

```java
int[][] deepRows = Arrays.stream(grid)
        .map(row -> row.clone())
        .toArray(int[][]::new);
deepRows[0][0] = 123;
// grid[0][0] vẫn là 99.
```

Đây là **deep copy ở cấp các mảng `int[]` bên trong**, phù hợp với `int[][]`. Nếu mảng nhiều chiều chứa **object mutable**, cần clone/copy cả object theo chính sách riêng; chỉ `row.clone()` vẫn là shallow ở cấp object.

## 11. Bảng xử lý ngoại lệ khi sửa mảng

| Lỗi | Tình huống điển hình | Thay đổi có thể đã xảy ra? | Cách phòng tránh |
| --- | --- | --- | --- |
| `ArrayIndexOutOfBoundsException` | `a[a.length] = 1`, `a[-1]` | Với một gán đơn lẻ bị lỗi thì ô đích không được ghi; nếu đang ở giữa vòng lặp, ô trước có thể đã đổi | Kiểm tra index/range trước vòng lặp |
| `IndexOutOfBoundsException` | `Objects.checkIndex` hoặc `System.arraycopy` phạm vi không hợp lệ | Phụ thuộc API; `arraycopy` quy định đích không đổi với lỗi phạm vi | Dùng `checkIndex`/`checkFromIndexSize` trước |
| `NullPointerException` | `a[0]` khi `a == null`, truyền null cho `Arrays.fill` | Có thể nếu lỗi ở giữa chuỗi thao tác khác | `Objects.requireNonNull` và hợp đồng đầu vào rõ |
| `NegativeArraySizeException` | `new int[-1]` | Không tạo được mảng mới | Xác thực size >= 0 trước khi cấp phát |
| `ArrayStoreException` | Lưu Integer vào mảng runtime `String[]`, hoặc `arraycopy` phần tử tham chiếu không tương thích | `arraycopy` có thể đã copy prefix hợp lệ | Chọn đúng runtime type; validate hoặc staging |
| `IllegalArgumentException` | `Arrays.sort/fill(a, from, to)` với `from > to` | Thao tác cụ thể sẽ kiểm tra phạm vi; không áp quy tắc đó cho mọi mã tự viết | Kiểm tra thứ tự biên |
| `ArithmeticException` | `Math.addExact`/`multiplyExact` bị overflow | Một vòng lặp in-place có thể đã sửa các phần trước | Kiểm tra độ rộng, staging, kiểu lớn hơn |
| `ClassCastException` | Object array sort theo natural order nhưng phần tử không so sánh được với nhau | Không tự bảo đảm array hoàn toàn chưa đổi | Kiểm tra kiểu và comparator |
| `UnsupportedOperationException` | Cố `add` trên `Arrays.asList`, không phải do array trực tiếp | Không thể thay đổi kích thước list view | Phân biệt view fixed-size với collection dynamic |

**Không dùng exception làm điều khiển vòng lặp thông thường.** Ví dụ cứ gán `a[i]` cho đến khi ném `ArrayIndexOutOfBoundsException` là thiết kế khó hiểu và có thể che lỗi. Dùng `for (int i=0; i<a.length; i++)` hoặc kiểm tra trước.

**Không bắt `Exception`/`RuntimeException` rộng chỉ để nuốt lỗi rồi tiếp tục dùng một mảng có thể đã hỏng trạng thái.** Hãy ghi rõ nguyên nhân, quy định có được retry/rollback hay không, và giữ bất biến nghiệp vụ nếu thao tác quan trọng.

## 12. Chương trình Java 17+ đầy đủ và kiểm thử được

Tạo tệp **`InPlaceArrayDemo.java`** với nội dung dưới đây:

```java
import java.util.*;
import java.util.function.*;
import java.util.stream.*;

public class InPlaceArrayDemo {
    static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    static void updateAllOrKeep(int[] array, IntUnaryOperator transform) {
        Objects.requireNonNull(array);
        Objects.requireNonNull(transform);
        int[] staged = array.clone();
        for (int i = 0; i < staged.length; i++) {
            staged[i] = transform.applyAsInt(staged[i]);
        }
        System.arraycopy(staged, 0, array, 0, array.length);
    }

    public static void main(String[] args) {
        int[] values = {4, 1, 3};
        int[] alias = values;
        alias[1] = 9;
        check(Arrays.equals(values, new int[]{4, 9, 3}), "alias");
        System.out.println("aliasMutatesOriginal=" +
                Arrays.toString(values));

        int[] copy = values.clone();
        copy[0] = 99;
        check(values[0] == 4 && copy[0] == 99, "copy");
        System.out.println("copyIndependent=" + Arrays.toString(copy));

        Arrays.fill(values, 1, 3, 7);
        System.out.println("afterFill=" + Arrays.toString(values));

        System.arraycopy(values, 0, values, 1, 2);
        System.out.println("afterOverlappingCopy=" +
                Arrays.toString(values));

        Arrays.sort(values);
        System.out.println("afterSort=" + Arrays.toString(values));

        Arrays.setAll(values, i -> i * 10);
        System.out.println("afterSetAll=" + Arrays.toString(values));

        values[Objects.checkIndex(2, values.length)] = 21;
        System.out.println("afterCheckedIndex=" +
                Arrays.toString(values));

        try {
            Objects.checkIndex(3, values.length);
            throw new AssertionError("should fail");
        } catch (IndexOutOfBoundsException expected) {
            System.out.println("invalidIndexCaught=true");
        }

        System.out.println("paddedRange=" +
                Arrays.toString(Arrays.copyOfRange(values, 1, 5)));

        // Một ArrayStoreException có thể xảy ra SAU khi copy prefix.
        String[] destination = {"start", "stay", "end"};
        Object[] mixed = {
                "copied", Integer.valueOf(42), "not copied"
        };
        try {
            System.arraycopy(mixed, 0, destination, 0, 3);
            throw new AssertionError(
                    "incompatible value should fail");
        } catch (ArrayStoreException expected) {
            System.out.println("partialArraycopy=" +
                    Arrays.toString(destination));
        }

        // Kiểu thật của mảng khác với kiểu biến Object[].
        Object[] covariant = new String[2];
        covariant[0] = "fine";
        try {
            covariant[1] = 5;
            throw new AssertionError("runtime type should fail");
        } catch (ArrayStoreException expected) {
            System.out.println("covariantStoreCaught=true");
        }

        // Copy mảng ngoài là shallow.
        int[][] grid = {{1, 2}, {3}};
        int[][] shallow = grid.clone();
        shallow[0][0] = 99;
        System.out.println("shallowChangesSource=" + grid[0][0]);

        int[][] deep = Arrays.stream(grid)
                .map(row -> row.clone())
                .toArray(int[][]::new);
        deep[0][0] = 123;
        System.out.println("deepCopyKeepsSource=" + grid[0][0]);

        // Staging ngăn phép tính lỗi làm thay đổi một phần mảng gốc.
        int[] atomicish = {1, 2, 3};
        try {
            updateAllOrKeep(atomicish,
                    v -> Math.multiplyExact(v, 1_000_000_000));
            throw new AssertionError("overflow must fail");
        } catch (ArithmeticException expected) {
            System.out.println("stagedFailurePreserved=" +
                    Arrays.toString(atomicish));
        }
        updateAllOrKeep(atomicish, v -> Math.multiplyExact(v, 10));
        System.out.println("successfulStagedUpdate=" +
                Arrays.toString(atomicish));

        // Pure generator: mỗi index cho kết quả độc lập.
        int[] parallel = new int[5];
        Arrays.parallelSetAll(parallel, i -> i * i);
        System.out.println("parallelSetAll=" + Arrays.toString(parallel));

        // Không dựa vào mảng ở trạng thái nào sau lỗi setAll.
        int[] uncertain = {9, 9, 9, 9};
        boolean failureCaught = false;
        try {
            Arrays.setAll(uncertain, i -> {
                if (i == 2) {
                    throw new IllegalStateException("index 2");
                }
                return i + 1;
            });
        } catch (IllegalStateException expected) {
            failureCaught = true;
        }
        check(failureCaught, "setAll failure");
        System.out.println("setAllFailureCaught=" + failureCaught);

        // View cố định kích thước được backing bởi String[].
        String[] names = {"A", "B"};
        List<String> view = Arrays.asList(names);
        view.set(0, "Z");
        System.out.println("asListBackedArray=" +
                Arrays.toString(names));

        System.out.println("ALL CHECKS PASSED");
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac InPlaceArrayDemo.java
java InPlaceArrayDemo
```

**Stdout mong đợi (chính xác):**

```text
aliasMutatesOriginal=[4, 9, 3]
copyIndependent=[99, 9, 3]
afterFill=[4, 7, 7]
afterOverlappingCopy=[4, 4, 7]
afterSort=[4, 4, 7]
afterSetAll=[0, 10, 20]
afterCheckedIndex=[0, 10, 21]
invalidIndexCaught=true
paddedRange=[10, 21, 0, 0]
partialArraycopy=[copied, stay, end]
covariantStoreCaught=true
shallowChangesSource=99
deepCopyKeepsSource=99
stagedFailurePreserved=[1, 2, 3]
successfulStagedUpdate=[10, 20, 30]
parallelSetAll=[0, 1, 4, 9, 16]
setAllFailureCaught=true
asListBackedArray=[Z, B]
ALL CHECKS PASSED
```

### 12.1. Giải thích dữ liệu và thứ tự thay đổi

1. `alias` trỏ đến cùng mảng với `values`; thay `alias[1]` làm `values` đổi thành `[4,9,3]`.
2. `copy = values.clone()` tạo mảng khác; `copy[0]=99` không thay đổi `values[0]`.
3. `Arrays.fill(values,1,3,7)` thay đúng hai ô index 1 và 2.
4. `arraycopy(values,0,values,1,2)` cho `[4,4,7]` vì mảng nguồn/đích chồng lấn được xử lý an toàn.
5. `Arrays.sort` thay mảng tại chỗ; `Arrays.setAll(values,i->i*10)` ghi giá trị theo **index**, không nhân đôi số cũ.
6. `Objects.checkIndex(2,3)` chấp nhận index 2; index 3 bị chặn **trước khi ghi**. `copyOfRange(values,1,5)` tạo mảng mới và đệm hai ô bằng zero.
7. `System.arraycopy` với `Object[]` chứa `Integer` vào `String[]` bị `ArrayStoreException` sau khi phần tử `"copied"` đã được copy. Đó là chứng cứ một lời gọi thất bại không nhất thiết để đích nguyên trạng.
8. Biến `Object[]` trỏ đến đối tượng `String[]` không cho phép lưu Integer. Runtime type được kiểm tra khi gán.
9. `grid.clone()` chỉ copy mảng ngoài, nên sửa row qua shallow copy tác động vào grid. Copy từng row bằng `row.clone()` tách các mảng con.
10. `Math.multiplyExact(3,1_000_000_000)` vượt `int`. Vì phép tính diễn ra trên `staged`, `atomicish` vẫn là `[1,2,3]`. Lần biến đổi an toàn nhân 10 mới được commit, ra `[10,20,30]`.
11. `parallelSetAll` dùng hàm chỉ phụ thuộc index nên cho kết quả chính xác bất kể thứ tự các tác vụ. Lỗi từ `setAll` được bắt nhưng **không có assertion về trạng thái mảng uncertain sau thất bại**.
12. `Arrays.asList(names)` trả List view backed by array: `view.set(0,"Z")` thay `names[0]`. View này có kích thước cố định, khác một `ArrayList` có thể thêm phần tử.

### 12.2. Những gì ví dụ cố ý không hứa

- Không hứa rằng `parallelSetAll` nhanh hơn `setAll`.
- Không hứa mảng được rollback sau exception từ generator.
- Không hứa staging + `System.arraycopy` là nguyên tử nếu có thread khác đang đọc mảng cùng lúc.
- Không hứa `Arrays.copyOf` tạo deep copy cho object array.
- Không in một thông báo lỗi hoặc stack trace JVM cố định: chúng có thể thay đổi theo phiên bản JDK.

## 13. `Arrays.asList` cũng có tác động “backed by array”

Trong Java, `Arrays.asList(T... a)` trả một List có kích thước cố định **được hỗ trợ trực tiếp bởi mảng tham chiếu đã truyền vào**. Khi gọi `set(index,value)`, mảng nguồn thay đổi và ngược lại:

```java
String[] names = {"A", "B"};
List<String> backed = Arrays.asList(names);

backed.set(1, "C");           // names bây giờ [A, C].
names[0] = "Z";               // backed.get(0) == "Z".
// backed.add("D");           // UnsupportedOperationException.
```

Đây là đoạn Java trong method đã import `java.util.*`. Điều này dễ gây lỗi khi caller tưởng `Arrays.asList` “copy thành List độc lập”.

**Đặc biệt với primitive array:**

```java
int[] ints = {1, 2, 3};
List<int[]> oneElement = Arrays.asList(ints);
int size = oneElement.size(); // 1, không phải 3.
```

Vì `int[]` không phải `Integer[]`, phương thức generic nhìn cả mảng primitive như **một phần tử tham chiếu**. Muốn một List<Integer> thực sự, có thể `Arrays.stream(ints).boxed().toList()`; cách đó tạo list object riêng từ các giá trị và không làm một backing view thay đổi cùng mảng primitive.

`Stream.toList()` trong Java 17+ trả một list không sửa được. Đừng lẫn nó với `Arrays.asList` fixed-size backed view.

## 14. An toàn luồng và chia sẻ mảng

**Mảng Java không tự đồng bộ các thao tác đọc/ghi theo một hợp đồng thread-safe**. Hai thread cùng thao tác `a[i]++` có thể mất cập nhật vì đó là tổ hợp đọc–cộng–ghi chứ không phải một primitive operation nguyên tử.

Với ứng dụng có nhiều thread, cân nhắc:

- **Không chia sẻ mảng mutable:** mỗi tác vụ dùng dữ liệu riêng, sau đó kết hợp kết quả dưới quyền sở hữu rõ ràng.
- **Khóa thích hợp:** đồng bộ mọi đường truy cập mảng dưới cùng lock khi cần trạng thái nhất quán.
- **AtomicIntegerArray/AtomicLongArray:** hỗ trợ cập nhật nguyên tử cho phần tử primitive tương ứng khi yêu cầu phù hợp; không đồng nghĩa giao dịch nhiều phần tử.
- **Snapshot bất biến theo phiên bản:** tính mảng mới rồi **công bố tham chiếu snapshot** bằng cơ chế có quan hệ happens-before thích hợp (ví dụ `volatile` reference/`AtomicReference`), các reader dùng cùng snapshot không sửa.

**Lưu ý:** Một biến `volatile int[] array` làm thao tác **đọc/ghi tham chiếu** có ngữ nghĩa volatile, chứ không tự biến mọi `array[index]` thành thao tác volatile. Nếu vẫn mutate cùng object array, các truy cập phần tử không tự được đồng bộ.

`Arrays.parallelSetAll` tự phối hợp việc điền giá trị theo từng chỉ số của một lời gọi, nhưng generator vẫn phải thỏa điều kiện không can thiệp và không sử dụng trạng thái mutable dùng chung tùy tiện. Không dùng nó để làm “parallel increment” nhiều thread trên cùng một ô.

## 15. Checklist kiểm thử sau khi sửa mảng

| Tình huống | Kỳ vọng cần khẳng định |
| --- | --- |
| Mảng rỗng | Không truy cập index 0; thao tác trên đoạn rỗng hợp lệ khi API hỗ trợ |
| Mảng một phần tử | Index 0 hợp lệ, index 1 không hợp lệ |
| Biên trái/phải | `from` inclusive, `to` exclusive; xử lý `from==to` |
| Mảng null | Bắt lỗi đầu vào trước khi có side effect khác |
| Aliasing | Sửa qua alias tác động vào cùng array; bản sao một chiều riêng thì không |
| `Arrays.fill` | Chỉ đoạn mục tiêu bị thay, phần ngoài đoạn được giữ |
| `System.arraycopy` có overlap | Kết quả như sao chép qua vùng tạm |
| `System.arraycopy` sai type phần tử | Có thể copy được prefix trước khi exception |
| `Arrays.setAll` bị exception | Không dùng trạng thái sau lỗi nếu hợp đồng không định nghĩa; thiết kế lại nếu cần rollback |
| Staging với phép biến đổi gây overflow | Mảng gốc giữ nguyên vì commit chưa chạy |
| Mảng hai chiều | Test row có chiều dài khác, shallow và deep copy |
| Object-array covariance | Runtime type check ném `ArrayStoreException` |
| Sorting | Dữ liệu đúng thứ tự, phần ngoài đoạn sort không đổi |
| Nhiều thread | Có chiến lược đồng bộ/ownership rõ, không test dựa trên một lịch chạy may mắn |

**Dùng `Arrays.equals` cho mảng một chiều** thay vì `array1.equals(array2)`: mảng không override `Object.equals` để so nội dung. Với mảng lồng nhau, cân nhắc `Arrays.deepEquals`; với log/test, `Arrays.deepToString` giúp xem cấu trúc lồng.

Ví dụ:

```java
int[] a = {1, 2};
int[] b = {1, 2};

boolean valuesEqual = Arrays.equals(a, b); // true
boolean sameObject = a == b;               // false
```

Hai phép so trả lời **hai câu hỏi khác nhau**. Khi kiểm tra đã copy độc lập hay chưa, có thể kiểm tra `a != b` và sửa b thử xem a còn nguyên.

## 16. Lỗi phổ biến trong chương trình Java thực tế

### Lỗi 1: Dùng `Arrays.copyOf` nhưng tưởng đã đổi mảng cũ

```java
int[] old = {1, 2};
Arrays.copyOf(old, 3); // Mảng mới bị bỏ đi; old vẫn dài 2.
```

**Sửa:** gán kết quả cho biến thích hợp, hoặc trả kết quả cho caller. Không thể kéo dài tại chỗ mảng Java.

### Lỗi 2: Sửa mảng input khi method hứa “không thay đổi dữ liệu”

Nếu public API nhận `int[] input` rồi gọi `Arrays.sort(input)`, caller sẽ thấy dữ liệu bị đảo. Nếu hợp đồng yêu cầu immutable input, hãy sort một bản sao:

```java
int[] sortedCopy = input.clone();
Arrays.sort(sortedCopy);
return sortedCopy;
```

Đây là **đoạn thân phương thức minh họa**, không chạy độc lập ở top-level; cần `input` là mảng non-null.

### Lỗi 3: Chỉ kiểm tra bounds ở mỗi vòng lặp sau khi đã sửa trước đó

Có thể khiến lỗi xuất hiện khi trạng thái đã bị thay đổi. **Sửa:** kiểm tra toàn bộ phạm vi trước; nếu vẫn có thể xảy ra lỗi bên trong phép biến đổi, staging.

### Lỗi 4: Giả định `setAll` có rollback

API đã nêu có thể để lại trạng thái không xác định khi generator lỗi. **Sửa:** generator pure, validation trước, hoặc xây bản sao rồi commit.

### Lỗi 5: Dùng `arraycopy` như một phép ép kiểu

`int[]` sang `long[]` không tự mở rộng; `Object[]` chứa giá trị không tương thích với `String[]` có thể làm copy một phần. **Sửa:** chuyển phần tử có kiểm tra kiểu, và dùng buffer nếu cần bảo đảm trạng thái đích.

### Lỗi 6: Quên object array lưu tham chiếu

`Arrays.fill(new StringBuilder[3], shared)` tạo nhiều alias, không tạo ba builder độc lập. **Sửa:** dùng `Arrays.setAll` để cấp phát riêng khi cần.

### Lỗi 7: Tưởng clone mảng nhiều chiều là deep copy

`int[][] copy = original.clone()` vẫn dùng chung các row. **Sửa:** clone mỗi row hoặc deep copy object theo ngữ nghĩa miền dữ liệu.

### Lỗi 8: Cố đọc phần tử qua iterator/Stream trong khi sửa array nguồn đồng thời

Đọc trên Stream từ mảng rồi mutate mảng bên ngoài có thể khiến dữ liệu không nhất quán và vi phạm yêu cầu non-interference của các Stream operation. **Sửa:** hoàn tất mutate trước khi tạo pipeline, hoặc xử lý bản sao dữ liệu.

### Lỗi 9: Dùng `parallel()` vì muốn thao tác nhanh hơn nhưng có side effect

Các generator/lamdba dùng biến đếm mutable chung có thể xảy ra race và cho kết quả không lặp lại. **Sửa:** dùng phép biến đổi độc lập theo index, thiết kế song song đúng và benchmark khi cần.

### Lỗi 10: Nuốt mọi exception rồi tiếp tục với mảng có thể bị hỏng

`catch (Exception ignored) {}` che trạng thái partial mutation. **Sửa:** mô tả rõ trạng thái sau lỗi, rollback theo chính sách hoặc chuyển mảng thất bại thành dữ liệu không được sử dụng.

## 17. Bài tập thực hành và đáp án

**Bài 1.** Mảng `int[] a={4,5,6,7}`. Sau `System.arraycopy(a,0,a,1,3)` thì là gì?

**Đáp án:** `[4,4,5,6]`. Nguồn và đích chồng lấn nhưng `arraycopy` bảo đảm ngữ nghĩa sao chép bằng bản tạm.

**Bài 2.** Mảng `int[] a={1,2,3,4,5}`. `Arrays.fill(a,1,4,0)` sửa những chỉ số nào?

**Đáp án:** `1,2,3`. Chỉ số `4` không thuộc phạm vi, vì `toIndex` là exclusive.

**Bài 3.** Vì sao `Object[] a = new String[2]; a[0]=100;` biên dịch được nhưng ném exception khi chạy?

**Đáp án:** Biến có kiểu Object[] nhưng runtime component type của array là String, nên gán Integer ném `ArrayStoreException`.

**Bài 4.** Có `int[][] a={{1},{2,3}}; int[][] b=a.clone(); b[0][0]=8;`. `a[0][0]` là gì?

**Đáp án:** `8` vì clone mảng ngoài vẫn dùng chung row tham chiếu.

**Bài 5.** Với `Arrays.setAll(a, i -> i*10)`, `i` là value cũ hay index?

**Đáp án:** Index. `a` được điền `0,10,20,...` theo chỉ số.

**Bài 6.** Nếu đang chạy vòng lặp in-place với `Math.multiplyExact` và phần tử cuối bị overflow, bắt `ArithmeticException` có làm các phần tử trước trở lại giá trị cũ không?

**Đáp án:** Không. Nếu cần “không đổi input khi lỗi”, tính trước vào mảng tạm rồi chỉ commit khi mọi phép tính thành công.

**Bài 7.** `Arrays.copyOfRange(new int[]{1,2,3},1,5)` cho gì?

**Đáp án:** `[2,3,0,0]`. `to` được phép vượt độ dài nguồn và phần thiếu được đệm mặc định; đây là tính năng của `copyOfRange`, không phải quy tắc cho mọi API phạm vi.

**Bài 8.** `final int[] a={1}; a[0]=2;` có hợp lệ không?

**Đáp án:** Có. `final` ngăn gán lại biến `a` nhưng không biến mảng thành immutable.

**Bài 9.** Có thể coi `System.arraycopy` là một bước commit atomic đối với nhiều thread không?

**Đáp án:** Không. Các phần tử được cập nhật, thread khác có thể quan sát dữ liệu không đồng nhất nếu thiếu đồng bộ. Khi cần snapshot, tạo mảng mới rồi công bố tham chiếu an toàn.

**Bài 10.** Muốn sort một mảng input nhưng không đổi input, cách đơn giản là gì?

**Đáp án:**

```java
int[] result = input.clone();
Arrays.sort(result);
```

Đoạn này cần `input != null` và được đặt trong một method. Nó phù hợp với mảng primitive một chiều; với mảng object/mảng lồng nhau phải xem yêu cầu bảo vệ object bên trong.

## 18. Checklist áp dụng vào production

- [ ] Có xác định rõ method **được phép mutate input** hay phải trả bản sao độc lập không?
- [ ] Đã kiểm tra aliasing qua tham số, field, array-backed list hoặc mảng con chưa?
- [ ] Đã phân biệt phần tử, runtime type, length cố định và nhu cầu resize chưa?
- [ ] Với mọi phép ghi theo chỉ số, đã kiểm tra vùng `[from,to)` hoặc `[from,from+length)` trước khi bắt đầu chưa?
- [ ] Đã hiểu `Arrays.fill`, `Arrays.setAll`, `Arrays.sort` là thao tác in-place; `copyOf/clone` tạo mảng mới?
- [ ] Với `System.arraycopy`, đã xét overlap, độ dài và khả năng lỗi giữa quá trình copy reference array?
- [ ] Với generator/lambda, đã tránh side effect, sửa mảng chéo index hoặc đọc trạng thái đang được cập nhật song song?
- [ ] Nếu lỗi ở giữa phép tính có thể gây thiệt hại, đã chọn validation/staging/commit hay trả kết quả mới?
- [ ] Đã test empty/singleton, phạm vi sai, null, type mismatch, overflow và partial mutation?
- [ ] Nếu mảng đa chiều hoặc chứa object mutable, đã xác định mức deep copy cần thiết?
- [ ] Nếu có nhiều thread, đã chọn owner/lock/atomic array/snapshot publication rõ ràng?
- [ ] Đã kiểm tra kết quả bằng `Arrays.equals` hoặc `deepEquals` thay vì chỉ dùng `==`?

## Tài liệu tham khảo chính thức đang áp dụng

1. [Oracle Java SE 26 — Arrays: fill, setAll, parallelSetAll, sort, parallelSort, copyOf, copyOfRange](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Arrays.html)
2. [Oracle Java SE 26 — System.arraycopy và hợp đồng overlap/partial copy](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/System.html)
3. [Oracle Java SE 26 — Objects.checkIndex/checkFromToIndex/checkFromIndexSize](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Objects.html)
4. [Oracle Java SE 26 — ArrayStoreException](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ArrayStoreException.html)
5. [Oracle Java SE 26 — AtomicIntegerArray khi cần cập nhật nguyên tử từng phần tử](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicIntegerArray.html)

**Ghi nhớ:** Thay đổi mảng tại chỗ có thể hiệu quả, nhưng chỉ an toàn khi hiểu **ai cùng giữ tham chiếu**, **phạm vi nào được phép sửa**, và **mảng còn ở trạng thái gì nếu có lỗi**. Không nhầm “đã bắt exception” với “đã rollback”; không nhầm “copy mảng” với “deep copy”; không nhầm “commit theo từng phần tử” với tính nguyên tử cho nhiều thread.
