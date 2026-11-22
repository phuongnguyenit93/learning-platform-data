# Kiểu mảng runtime và nguy cơ lỗi kiểu

## 1. Hai lớp thông tin cần phân biệt

Khi làm việc với mảng, có hai câu hỏi khác nhau:

- **Kiểu khai báo của biến là gì?** Trình biên dịch dùng thông tin này để kiểm tra các biểu thức.
- **Đối tượng mảng thực sự có kiểu gì khi chạy (runtime type)?** JVM dùng thông tin này để kiểm tra phần tử có được phép lưu vào mảng hay không và phép ép kiểu có hợp lệ hay không.

Ví dụ minh họa:

```java
String[] words = {"north", "south"};
Object[] values = words;
```

Biến `values` có kiểu khai báo `Object[]`, nhưng vẫn trỏ tới chính đối tượng `String[]`. Câu lệnh gán không tạo mảng mới và không đổi mảng đó thành `Object[]`.

Quan hệ cho phép gán `String[]` vào `Object[]` được gọi là **tính đồng biến của mảng (array covariance)**: nếu `String` là kiểu con của `Object`, `String[]` cũng có thể dùng tại nơi nhận `Object[]`.

Sự linh hoạt này đi cùng kiểm tra lúc chạy. Nếu sau đó viết `values[0] = Integer.valueOf(5);`, mã biên dịch được nhưng bị JVM từ chối bằng `ArrayStoreException`, vì đối tượng mảng thật chỉ chứa được tham chiếu `String` hoặc `null`.

Các quy tắc này vẫn áp dụng trong Java hiện đại, theo [JLS §10.5 về kiểm tra khi lưu vào mảng](https://docs.oracle.com/javase/specs/jls/se25/html/jls-10.html#jls-10.5). Các ví dụ đầy đủ trong bài chạy bằng Java 17+.

## 2. Sao chép không tự chọn kiểu rộng hơn theo biến nhận

Với biến thể hai tham số cho mảng tham chiếu:

```java
Object[] copied = Arrays.copyOf(values, 3);
```

Nếu đối tượng nguồn thật là `String[]`, đối tượng kết quả cũng là `String[]`. Kiểu khai báo `Object[]` của biến nhận không làm kết quả trở thành một mảng có thể chứa mọi đối tượng.

Đó là hợp đồng của `Arrays.copyOf(T[], int)`: mảng mới có cùng lớp lúc chạy với nguồn. Biến thể `copyOfRange(T[], int, int)` không có tham số kiểu đích cũng giữ lớp của nguồn. Xem [tài liệu Arrays về các biến thể sao chép](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html).

Có thể hình dung:

```text
Kiểu biến nguồn:       Object[]
Đối tượng nguồn:       String[]

Arrays.copyOf(...):
Kiểu biến nhận:        Object[]
Đối tượng kết quả:     String[]   <- giữ kiểu thật của nguồn
```

Phần tăng thêm của mảng tham chiếu được điền `null`. Giá trị `null` hợp lệ trong `String[]`, nhưng một số nguyên hay đối tượng khác thì không.

Khi thật sự muốn đổi kiểu mảng kết quả, hãy dùng biến thể có tham số kiểu:

```java
Object[] copied = Arrays.copyOf(values, 3, Object[].class);
```

Lần này mảng kết quả có kiểu lúc chạy là `Object[]`, nên có thể chứa cả chuỗi và số nguyên đóng hộp.

Tham số thứ ba là lớp của **mảng**, chẳng hạn `Object[].class`, `Number[].class` hoặc `String[].class`; không phải lớp phần tử như `Object.class`.

## 3. Ví dụ chạy đầy đủ: giữ kiểu, đổi kiểu và ép kiểu

Lưu thành `RuntimeArrayCopyDemo.java`:

```java
import java.util.Arrays;

public class RuntimeArrayCopyDemo {
    public static void main(String[] args) {
        String[] directions = {"north", "south"};
        Object[] viewedAsObjects = directions;

        Object[] preserved = Arrays.copyOf(viewedAsObjects, 3);
        System.out.println("source type: "
                + viewedAsObjects.getClass().getTypeName());
        System.out.println("copy type: "
                + preserved.getClass().getTypeName());

        try {
            preserved[2] = Integer.valueOf(5);
        } catch (ArrayStoreException e) {
            System.out.println("store rejected by String array");
        }

        Object[] widened =
                Arrays.copyOf(viewedAsObjects, 3, Object[].class);
        widened[2] = Integer.valueOf(5);
        System.out.println("widened type: "
                + widened.getClass().getTypeName());
        System.out.println("widened values: " + Arrays.toString(widened));

        Object[] plainObjects = {"left", "right"};
        try {
            String[] invalidCast = (String[]) plainObjects;
            System.out.println(Arrays.toString(invalidCast));
        } catch (ClassCastException e) {
            System.out.println("cast rejected by Object array");
        }

        String[] realStrings =
                Arrays.copyOf(plainObjects, plainObjects.length,
                        String[].class);
        System.out.println("new String array: "
                + Arrays.toString(realStrings));

        Object[] mixed = {"ok", Integer.valueOf(42)};
        String[] prefix = Arrays.copyOf(mixed, 1, String[].class);
        System.out.println("compatible prefix: " + Arrays.toString(prefix));

        try {
            Arrays.copyOf(mixed, 2, String[].class);
        } catch (ArrayStoreException e) {
            System.out.println("incompatible copied element rejected");
        }

        String[] destination = {"old0", "old1"};
        try {
            System.arraycopy(mixed, 0, destination, 0, mixed.length);
        } catch (ArrayStoreException e) {
            System.out.println("arraycopy destination: "
                    + Arrays.toString(destination));
        }
    }
}
```

Biên dịch và chạy:

```shell
javac RuntimeArrayCopyDemo.java
java RuntimeArrayCopyDemo
```

Stdout:

```text
source type: java.lang.String[]
copy type: java.lang.String[]
store rejected by String array
widened type: java.lang.Object[]
widened values: [north, south, 5]
cast rejected by Object array
new String array: [left, right]
compatible prefix: [ok]
incompatible copied element rejected
arraycopy destination: [ok, old1]
```

Các phép thử được đặt trong `try/catch` để chương trình tiếp tục minh họa từng trường hợp. Trong mã nghiệp vụ, nên thiết kế đúng kiểu dữ liệu thay vì dùng ngoại lệ làm cách kiểm tra thường xuyên.

## 4. Vì sao có hai loại ngoại lệ?

### ArrayStoreException: phần tử không hợp với mảng đích

Một thao tác ghi vào mảng phải tuân theo kiểu phần tử thật của mảng đó.

Trong chương trình:

```java
preserved[2] = Integer.valueOf(5);
```

Biến `preserved` được khai báo `Object[]`, nên trình biên dịch cho phép biểu thức bên phải. Nhưng mảng thật là `String[]`, nên JVM từ chối lần lưu.

Ngoại lệ tương tự có thể xảy ra trong khi sao chép sang mảng đích hẹp hơn:

```java
Object[] mixed = {"ok", Integer.valueOf(42)};
String[] copied = Arrays.copyOf(mixed, 2, String[].class);
```

Đoạn này minh họa lỗi, không phải chương trình độc lập. Chuỗi `"ok"` lưu được trong `String[]`; `Integer` thì không. Việc sao chép không hoàn thành để trả mảng kết quả về.

Nếu chỉ yêu cầu sao chép một phần tử đầu, thao tác thành công. Điều kiện tương thích áp dụng cho các phần tử **thực sự được sao chép**, không phải cho mọi phần tử có thể tồn tại ngoài đoạn được lấy.

Phương thức không tự chuyển `Integer` thành chuỗi `"42"`. Chuyển đổi giá trị là một bước riêng, cần quy tắc rõ ràng.

### ClassCastException: chính đối tượng mảng không thuộc kiểu muốn ép

Trong chương trình:

```java
Object[] plainObjects = {"left", "right"};
String[] invalidCast = (String[]) plainObjects;
```

Đối tượng được tạo ra là `Object[]`. Mọi phần tử hiện tại đều là chuỗi cũng không làm lớp của mảng đổi thành `String[]`.

Phép ép kiểu kiểm tra đối tượng mảng, không chạy qua các ô để tạo một mảng khác. Vì đối tượng không phải `String[]`, phép ép thất bại bằng `ClassCastException`.

Ngược lại, khi một biến `Object[]` thực sự trỏ đến `String[]`, ép nó trở lại `String[]` là hợp lệ. Điều quyết định là kiểu thật, không phải chỉ tên kiểu của biến.

| Tình huống | Loại kiểm tra | Lỗi điển hình |
| --- | --- | --- |
| Lưu `Integer` vào đối tượng `String[]` | Phần tử có chứa được trong mảng không? | `ArrayStoreException` |
| Sao chép phần tử không tương thích vào mảng đích có kiểu hẹp | Phần tử được sao chép có chứa được không? | `ArrayStoreException` |
| Ép đối tượng `Object[]` thật thành `String[]` | Đối tượng mảng có đúng kiểu không? | `ClassCastException` |
| Gán trực tiếp `new Object[2]` cho biến `String[]` mà không ép | Kiểm tra kiểu tĩnh | Lỗi biên dịch |

## 5. Chọn kiểu đích rõ ràng thay cho ép kiểu mò

Khi cần một mảng `String[]` từ nguồn khai báo `Object[]`, có hai bài toán rất khác nhau.

### Sao chép các phần tử vốn đã là String

Nếu từng phần tử cần giữ đều là `String` hoặc `null`, dùng:

```java
String[] strings =
        Arrays.copyOf(objects, objects.length, String[].class);
```

Đây là mẫu thao tác, giả sử biến `objects` đã tồn tại. Phương thức tạo một mảng `String[]` thật và kiểm tra tính tương thích khi sao chép.

Phần tử `null` có thể được lưu trong mảng tham chiếu. Tuy nhiên, việc chấp nhận `null` về mặt kiểu không có nghĩa mọi đoạn xử lý phía sau chấp nhận nó về mặt nghiệp vụ.

### Chuyển các đối tượng khác thành chuỗi

Nếu nguồn có số nguyên, ngày tháng hoặc đối tượng nghiệp vụ mà bạn muốn biểu diễn thành văn bản, cần bước chuyển đổi từng phần tử. Ví dụ minh họa:

```java
Object[] objects = {"count", Integer.valueOf(42)};
String[] strings = new String[objects.length];

for (int i = 0; i < objects.length; i++) {
    strings[i] = String.valueOf(objects[i]);
}
```

Kết quả là `["count", "42"]`. Đây là chuyển đổi nội dung, không chỉ sao chép tham chiếu. `String.valueOf(Object)` biến `null` thành chuỗi `"null"`; nếu điều đó không phù hợp, cần chọn cách xử lý khác.

Không thêm một phép ép kiểu chỉ để làm trình biên dịch im lặng. Hãy xác định mình muốn **giữ các giá trị tương thích** hay **tạo các giá trị đã chuyển đổi**.

## 6. Bẫy trong phương thức generic mở rộng mảng

Một phương thức có tham số kiểu `T` vẫn phải tôn trọng kiểu thật của mảng. Việc bên gọi chọn `T = Object` không thể đổi `String[]` đã được tạo trước đó thành `Object[]`.

Lưu thành `GenericArrayAppendDemo.java`:

```java
import java.util.Arrays;

public class GenericArrayAppendDemo {
    static <T> T[] appendKeepingRuntimeType(T[] source, T value) {
        T[] result = Arrays.copyOf(source, source.length + 1);
        result[source.length] = value;
        return result;
    }

    static Object[] appendAsObjects(Object[] source, Object value) {
        Object[] result =
                Arrays.copyOf(source, source.length + 1, Object[].class);
        result[source.length] = value;
        return result;
    }

    public static void main(String[] args) {
        String[] words = {"red"};

        try {
            Object[] result =
                    GenericArrayAppendDemo.<Object>appendKeepingRuntimeType(
                            words, Integer.valueOf(9));
            System.out.println(Arrays.toString(result));
        } catch (ArrayStoreException e) {
            System.out.println("generic append still kept String array");
        }

        Object[] result = appendAsObjects(words, Integer.valueOf(9));
        System.out.println("explicit result type: "
                + result.getClass().getTypeName());
        System.out.println("explicit result: " + Arrays.toString(result));
        System.out.println("source: " + Arrays.toString(words));
    }
}
```

Biên dịch và chạy:

```shell
javac GenericArrayAppendDemo.java
java GenericArrayAppendDemo
```

Stdout:

```text
generic append still kept String array
explicit result type: java.lang.Object[]
explicit result: [red, 9]
source: [red]
```

Vì sao lần gọi đầu vẫn biên dịch được?

1. Bên gọi chỉ rõ tham số kiểu là `Object`.
2. `String[]` truyền được cho tham số `Object[]` nhờ tính đồng biến.
3. Giá trị `Integer` cũng là một `Object`.
4. Nhưng `copyOf` hai tham số vẫn tạo `String[]` theo nguồn thật.
5. Lần ghi số nguyên vào phần tử mới gây `ArrayStoreException`.

Phiên bản `appendAsObjects` thể hiện hợp đồng khác: kết quả luôn là `Object[]` thật. Nó phù hợp khi kết quả được phép chứa nhiều kiểu đối tượng.

Nếu yêu cầu là giữ `String[]`, cách sửa phù hợp lại là chỉ thêm `String` hoặc `null`, chứ không làm rộng mảng tùy tiện. Thiết kế API phải quyết định mình cần kiểu mảng nào.

## 7. Lỗi khi sao chép có thể để lại điều gì?

Với `Arrays.copyOf` hoặc `copyOfRange`, mảng đích mới do phương thức tạo. Nếu gặp lỗi kiểu trong quá trình sao chép, lời gọi không trả về một mảng hoàn chỉnh cho bên gọi. Chính thao tác sao chép không sửa các ô trong mảng nguồn.

Câu lệnh gán kết quả chỉ diễn ra khi vế phải hoàn tất. Ví dụ minh họa:

```java
String[] current = {"previous"};
Object[] incoming = {"ok", Integer.valueOf(42)};

try {
    current = Arrays.copyOf(incoming, incoming.length, String[].class);
} catch (ArrayStoreException e) {
    // current van giu mang {"previous"}.
}
```

Với `System.arraycopy`, đích là một mảng đã tồn tại. Nếu nguồn và đích là mảng tham chiếu, một số phần tử đầu có thể đã được chép trước khi gặp phần tử không tương thích.

Trong chương trình `RuntimeArrayCopyDemo`, đích từ `["old0", "old1"]` trở thành `["ok", "old1"]` khi ngoại lệ được bắt. Không được coi lần sao chép đó là một giao dịch “hoặc thành công hết, hoặc không đổi gì”.

Hành vi sao chép tiền tố trước lỗi kiểu được quy định trong [System.arraycopy](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#arraycopy(java.lang.Object,int,java.lang.Object,int,int)). Không suy rộng rằng mọi loại lỗi của `arraycopy` đều thay đổi một phần đích; cần phân biệt lỗi phần tử không tương thích với các lỗi kiểm tra đối số khác.

## 8. Mảng nguyên thủy không tự chuyển kiểu cả mảng

Quy tắc mở rộng kiểu số của một giá trị không tự áp dụng cho cả mảng:

```java
int[] source = {1, 2};
// long[] invalid = source; // Khong bien dich.
```

Dù một giá trị `int` có thể được gán cho một biến `long`, `int[]` không phải kiểu con của `long[]`.

Mọi mảng đều là đối tượng, nên có thể gán `int[]` cho biến `Object`. Nhưng `int[]` không phải `Object[]`; kiểu phần tử `int` không phải kiểu tham chiếu `Object`.

Các hệ quả thực tế:

- `Arrays.copyOf(intArray, n)` trả về `int[]`, không phải `long[]` hoặc `Integer[]`.
- Không dùng biến thể ba tham số cho mảng tham chiếu để chuyển một `int[]` thành `Integer[]`.
- Ép một `Object` đang trỏ đến `int[]` thành `Object[]` gây `ClassCastException`.
- `System.arraycopy` từ `int[]` sang `long[]` không tự mở rộng từng số; khác kiểu nguyên thủy là lỗi kiểu.

Nếu cần `long[]`, tạo mảng đích và chuyển từng giá trị theo quy tắc số. Nếu cần `Integer[]`, cần thực hiện đóng hộp từng phần tử.

## 9. Cách kiểm tra trước khi quyết định sao chép

Khi gặp lỗi kiểu, có thể quan sát:

```java
System.out.println(array.getClass().getTypeName());
System.out.println(array.getClass().getComponentType().getTypeName());
```

Đoạn chẩn đoán này giả sử biến `array` là một mảng khác `null`. Với đối tượng `String[]`, hai dòng tương ứng là `java.lang.String[]` và `java.lang.String`.

Sau đó kiểm tra:

1. Nguồn thật là mảng gì, không chỉ biến đang được khai báo thế nào?
2. Bạn muốn giữ kiểu nguồn hay tạo mảng đích có kiểu khác?
3. Các phần tử nằm trong đoạn cần sao chép có tương thích với kiểu đích không?
4. Có cần chuyển đổi giá trị thay vì chỉ sao chép tham chiếu không?
5. Đích là mảng mới hay một mảng cũ có thể bị thay đổi một phần?
6. Mã generic có đang giả định rằng kiểu `T` đã làm rộng kiểu thật của mảng không?

Tự kiểm tra:

- `Number[] x = new Integer[2]; x[0] = Double.valueOf(1.5);` gây gì? **`ArrayStoreException`; mảng thật là `Integer[]`.**
- `Object[] x = {"A"}; (String[]) x` có hợp lệ chỉ vì mọi phần tử là chuỗi không? **Không; mảng thật là `Object[]`, nên ép kiểu thất bại.**
- Sao chép từ một `String[]` bằng hai tham số rồi nhận vào `Object[]` có đổi kiểu thật không? **Không; bản sao vẫn là `String[]`.**
- Muốn bản sao thật là `Object[]` cần thể hiện điều gì? **Chọn kiểu đích rõ ràng, chẳng hạn tham số `Object[].class`.**
- Một lần `arraycopy` gặp phần tử không tương thích có luôn giữ nguyên toàn bộ đích không? **Không; các phần tử tương thích đứng trước có thể đã được chép.**
