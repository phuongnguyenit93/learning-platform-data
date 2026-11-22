# Phân biệt `int[]` với `Integer[]` và khả năng gán qua `Object` trong Java

## 1. Hai kiểu mảng khác nhau

Trong Java, `int[]` và `Integer[]` đều là **kiểu tham chiếu trỏ đến đối tượng mảng**, nhưng **kiểu phần tử** khác nhau:

| Tiêu chí | `int[]` | `Integer[]` |
| --- | --- | --- |
| Kiểu phần tử | Nguyên thủy `int` | Tham chiếu đến đối tượng `java.lang.Integer` |
| Giá trị mặc định của phần tử trong mảng mới | `0` | `null` |
| Một phần tử có thể là `null`? | Không | Có |
| Gán phần tử từ giá trị `int` | Trực tiếp | Autoboxing `int` thành `Integer` |
| Đọc một phần tử vào biến `int` | Trực tiếp | Unboxing; có thể gây `NullPointerException` khi phần tử `null` |
| Gán cả mảng cho `Object` | Được | Được |
| Gán cả mảng cho `Object[]` | **Không được** | **Được** |
| Đổi trực tiếp `int[]` thành `Integer[]` bằng cast/autoboxing | Không | Không áp dụng |

Mỗi đối tượng mảng có `length` cố định sau khi khởi tạo. `int[]` thường tiết kiệm bộ nhớ và tránh boxing khi xử lý dữ liệu số; `Integer[]` phù hợp khi cần phần tử `null` hoặc một API yêu cầu tham chiếu `Integer`. Không thể coi hai kiểu mảng này là hoán đổi cho nhau.

```java
int[] primitive = new int[3];     // [0, 0, 0]
Integer[] wrappers = new Integer[3]; // [null, null, null]

primitive[0] = 10;
wrappers[0] = 10; // autoboxing: Integer.valueOf(10)

int a = primitive[0]; // 10
int b = wrappers[0];  // unboxing: intValue(), kết quả 10
```

Các lệnh trên là **đoạn minh họa đặt bên trong phương thức**, không phải chương trình độc lập. Nếu `wrappers[1]` đang là `null`, phép gán `int x = wrappers[1]` gây `NullPointerException`.

## 2. Vì sao cả hai đều gán được cho `Object`, nhưng chỉ một loại gán được cho `Object[]`?

Trong Java, **bản thân mảng luôn là đối tượng**: mọi kiểu mảng, kể cả mảng chứa phần tử nguyên thủy, đều có thể gán cho `Object`. Chúng còn triển khai `Cloneable` và `java.io.Serializable`.

```java
int[] a = {1, 2};
Integer[] b = {1, 2};

Object oa = a; // Hợp lệ: Object giữ tham chiếu tới int[]
Object ob = b; // Hợp lệ: Object giữ tham chiếu tới Integer[]

Object[] refs = b; // Hợp lệ: Integer là kiểu tham chiếu
// Object[] invalid = a; // LỖI BIÊN DỊCH: int[] không phải Object[]
```

`Object[]` là mảng có **các phần tử là tham chiếu đối tượng**. `Integer[]` là mảng của các tham chiếu `Integer` (một kiểu con của `Object`), nên có thể gán cho `Object[]`. Ngược lại, phần tử của `int[]` là giá trị nguyên thủy; `int` **không phải kiểu con** của `Object`, vì vậy `int[]` không thể gán cho `Object[]`.

Một phép gán mảng sang `Object` **không biến đổi các phần tử**:

- `Object o = new int[]{1, 2};` chỉ lưu tham chiếu đến **chính mảng `int[]`**.
- `(int[]) o` trả lại tham chiếu theo kiểu `int[]` khi đối tượng thực sự có kiểu đó.
- `(Integer[]) o` không chuyển kiểu từng phần tử; nếu `o` thực sự trỏ tới `int[]`, phép cast này gây `ClassCastException`.
- Autoboxing `int` → `Integer` và unboxing `Integer` → `int` áp dụng cho **giá trị riêng lẻ**, không tự chuyển toàn bộ `int[]` ↔ `Integer[]`.

## 3. Mảng nhiều chiều: `int[][]` lại có thể gán cho `Object[]`

Đây là điểm đặc biệt dễ nhầm trong chủ đề mảng nhiều chiều. Trong Java, `int[][]` là một **mảng ngoài**, mỗi phần tử của nó là **một tham chiếu tới `int[]`**. Vì `int[]` là một đối tượng nên phần tử của mảng ngoài là kiểu tham chiếu.

```java
int[][] matrix = {{10, 20}, {30}};
Object asObject = matrix;   // Hợp lệ: mọi mảng đều là Object
Object[] rows = matrix;     // Hợp lệ: mỗi phần tử của matrix là int[]
Object first = rows[0];     // Đối tượng thật là int[]
int[] firstRow = (int[]) first;
int item = firstRow[1];     // 20

// Object[][] invalid = matrix; // LỖI: int[][] không phải Object[][]
```

So sánh ba tầng:

| Kiểu biểu thức | Bản chất đối tượng mảng | Gán được cho `Object[]`? |
| --- | --- | --- |
| `int[]` | Các phần tử là `int` nguyên thủy | Không |
| `Integer[]` | Các phần tử là tham chiếu `Integer` | Có |
| `int[][]` | Các phần tử là tham chiếu `int[]` | Có |

Độ sâu quan trọng: `int[][]` là `Object[]`, nhưng mỗi hàng `matrix[i]` vẫn có kiểu `int[]` và **không thể** gán trực tiếp cho `Object[]`. Tương tự, `Integer[][]` có thể gán cho `Object[][]`, vì mỗi hàng `Integer[]` là một `Object[]`.

## 4. Tính hiệp biến và kiểm tra kiểu khi ghi qua `Object[]`

Mảng các kiểu tham chiếu trong Java **hiệp biến** (*covariant*): nếu `Integer` là kiểu con của `Number` và `Object`, thì `Integer[]` gán được cho `Number[]` và `Object[]`.

```java
Integer[] numbers = {1, 2};
Number[] asNumbers = numbers;
Object[] asObjects = numbers;
asObjects[0] = Integer.valueOf(10); // Hợp lệ
// asObjects[1] = "hello";          // Biên dịch được, nhưng lỗi khi chạy
```

Do `asObjects` và `numbers` cùng trỏ tới **mảng thực có kiểu `Integer[]`**, JVM kiểm tra kiểu đối tượng lúc gán phần tử. Dù biến có kiểu `Object[]`, gán `String` vào mảng thực `Integer[]` sẽ ném **`ArrayStoreException`**. Điều này cũng áp dụng cho `Object[] rows = new int[2][]`: chỉ có thể lưu `int[]` hoặc `null` vào từng phần tử, không thể lưu `Integer[]`.

Đừng nhầm `ArrayStoreException` khi gán sai kiểu cho **phần tử mảng tham chiếu** với `ClassCastException` khi **ép kiểu chính đối tượng mảng**.

## 5. Chương trình Java 17+ có thể chạy độc lập

Tạo tệp **`ArrayTypeDemo.java`**:

```java
import java.util.Arrays;

public class ArrayTypeDemo {
    public static void main(String[] args) {
        int[] raw = {1, 2, 3};
        Integer[] wrapped = {1, null, 3};

        Object rawAsObject = raw;
        Object wrappedAsObject = wrapped;
        System.out.println("raw la Object: " + (rawAsObject instanceof Object));
        System.out.println("raw la Object[]: " + (rawAsObject instanceof Object[]));
        System.out.println("wrapped la Object[]: " + (wrappedAsObject instanceof Object[]));

        Object[] elements = wrapped;
        elements[0] = 99;  // Autoboxing; thay đổi mảng wrapped gốc
        System.out.println("wrapped: " + Arrays.toString(wrapped));

        try {
            elements[1] = "wrong"; // JVM chặn do mảng thực là Integer[]
        } catch (ArrayStoreException ex) {
            System.out.println("Gan sai kieu: ArrayStoreException");
        }

        int[][] matrix = {{10, 20}, {30}};
        Object[] rows = matrix;
        System.out.println("matrix la Object[]: " + (matrix instanceof Object[]));
        System.out.println("rows[0] la int[]: " + (rows[0] instanceof int[]));
        rows[1] = new int[]{40, 50};
        System.out.println("Hang thu 2: " + Arrays.toString(matrix[1]));

        try {
            rows[0] = new Integer[]{7}; // Phần tử thực phải là int[]
        } catch (ArrayStoreException ex) {
            System.out.println("Gan sai hang: ArrayStoreException");
        }

        System.out.println("asList(int[]): " + Arrays.asList(raw).size());
        System.out.println("asList(Integer[]): " + Arrays.asList(wrapped).size());

        Integer[] boxedCopy = Arrays.stream(raw).boxed().toArray(Integer[]::new);
        int[] primitiveCopy = Arrays.stream(boxedCopy)
                                    .mapToInt(Integer::intValue).toArray();
        System.out.println("Boxed: " + Arrays.toString(boxedCopy));
        System.out.println("Unboxed: " + Arrays.toString(primitiveCopy));
    }
}
```

Trong thư mục chứa tệp, sử dụng JDK 17 trở lên:

```bash
javac -encoding UTF-8 ArrayTypeDemo.java
java ArrayTypeDemo
```

Kết quả stdout chính xác (biên dịch thành công không in thông báo):

```text
raw la Object: true
raw la Object[]: false
wrapped la Object[]: true
wrapped: [99, null, 3]
Gan sai kieu: ArrayStoreException
matrix la Object[]: true
rows[0] la int[]: true
Hang thu 2: [40, 50]
Gan sai hang: ArrayStoreException
asList(int[]): 1
asList(Integer[]): 3
Boxed: [1, 2, 3]
Unboxed: [1, 2, 3]
```

Giải thích: `elements` là tham chiếu kiểu `Object[]` đến cùng đối tượng `Integer[]` với `wrapped`, nên sửa `elements[0]` ảnh hưởng `wrapped[0]`. `rows` trỏ tới cùng mảng ngoài `matrix`, vì vậy thay `rows[1]` làm đổi hàng thứ hai của `matrix`. Cả hai phép ghi sai kiểu đều bị JVM chặn tại thời điểm chạy.

## 6. Chuyển đổi nội dung mảng khi thật sự cần

Vì không có phép chuyển toàn mảng tự động, hãy **tạo mảng mới** và chuyển từng phần tử.

**Từ `int[]` sang `Integer[]`:**

```java
int[] source = {5, 6};
Integer[] boxed = java.util.Arrays.stream(source)
                                  .boxed()
                                  .toArray(Integer[]::new);
// boxed có nội dung [5, 6]
```

**Từ `Integer[]` sang `int[]`:**

```java
Integer[] source = {5, 6};
int[] plain = java.util.Arrays.stream(source)
                              .mapToInt(Integer::intValue)
                              .toArray();
// plain có nội dung [5, 6]
```

Hai đoạn là mã minh họa bên trong phương thức; ví dụ ở mục 5 là chương trình chạy hoàn chỉnh. Nếu `Integer[]` chứa `null`, phép unboxing tại `Integer::intValue` gây `NullPointerException`. Phải quyết định cách xử lý `null` tùy bài toán trước khi chuyển (ví dụ từ chối dữ liệu, bỏ qua, hoặc thay bằng giá trị mặc định có chủ đích).

**Một lỗi API liên quan:** `Arrays.asList(raw)` với `raw` là `int[]` tạo danh sách có **một phần tử là cả mảng `int[]`**; `Arrays.asList(wrapped)` với `wrapped` là `Integer[]` tạo danh sách các `Integer` theo từng phần tử. Trong ví dụ chạy, kích thước lần lượt là `1` và `3`. Để lấy `List<Integer>` từ `int[]`, dùng `Arrays.stream(raw).boxed().toList()` (Java 16+); kết quả này là danh sách các giá trị đã boxing.

## 7. Lỗi phổ biến và cách ghi nhớ

- `int[]` là mảng **chứa nguyên thủy**, nhưng bản thân **vẫn là đối tượng**, do đó gán được cho `Object`.
- `Object[]` yêu cầu **kiểu phần tử là tham chiếu**: nhận `Integer[]`, `String[]`, `int[][]`; **không nhận** `int[]`.
- Không dùng `(Integer[]) someIntArray` để boxing cả mảng; phép cast không chuyển phần tử, cần tạo mảng mới.
- Tránh unboxing `Integer` chứa `null` mà không kiểm tra.
- Qua biến `Object[]`, phép ghi vẫn bị kiểm tra theo kiểu mảng thật ở runtime; `ArrayStoreException` bảo vệ tính đúng đắn của mảng.
- Với mảng nhiều chiều, luôn xem **kiểu phần tử của tầng đang xét**: `int[][]` chứa phần tử `int[]` (tham chiếu), còn `int[]` chứa phần tử `int` (nguyên thủy).

**Quy tắc cốt lõi:** loại dữ liệu của **phần tử mảng** quyết định mảng đó có thể là `Object[]` hay không; sự thật “mảng là đối tượng” chỉ đủ để gán **cả mảng** cho `Object`.