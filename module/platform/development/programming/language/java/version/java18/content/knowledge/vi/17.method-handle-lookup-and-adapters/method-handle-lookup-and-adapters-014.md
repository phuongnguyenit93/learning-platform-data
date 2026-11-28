# `asSpreader()`: chuyển đối số mảng thành các tham số của handle đích

## 1. Bối cảnh và mục tiêu

Bài học thuộc chương **Lookup và adapter**, module **JAVA_VERSION_JAVA18**. `java.lang.invoke.MethodHandle` là tham chiếu có kiểu tới một thao tác thực thi. Khi ứng dụng đã có một handle nhận nhiều tham số riêng lẻ nhưng dữ liệu đầu vào được chứa trong **một mảng**, `asSpreader()` tạo một handle mới để phân phối từng phần tử mảng vào những vị trí tham số tương ứng.

Ví dụ: hàm đích nhận `(int, int, int)`, còn bộ điều phối có một số nguyên cố định và một mảng `int[]` chứa hai số nguyên còn lại. Adapter cho phép chuyển từ kiểu gọi `(int, int, int)int` thành `(int, int[])int`.

Sau bài học, bạn có thể:

- Dự đoán chính xác `MethodType` trước và sau khi gọi `asSpreader()`.
- Dùng overload trải **các đối số cuối** và overload chỉ định **vị trí bắt đầu trải**.
- Giải thích cách chọn `arrayType`, `arrayLength`, vị trí phần tử và mối liên hệ với `invokeExact()`.
- Phân biệt lỗi tạo adapter, lỗi mảng sai chiều dài, lỗi thiếu tham số và lỗi kiểu tại call site.
- Chọn giữa `asSpreader()`, `asCollector()` và `invokeWithArguments()` tùy hình dạng dữ liệu thực tế.

**Phạm vi Java 18 và JDK hiện đại:** `MethodHandle` tồn tại từ trước Java 18; Java 18 có JEP 416, triển khai lại core reflection dựa trên method handles và variable handles. Nội dung `asSpreader()` ở đây là **API công khai vẫn được hỗ trợ**, không phải tính năng mới xuất hiện lần đầu ở Java 18. Chúng ta chỉ sử dụng `java.lang.invoke` và các API Java chuẩn, không dựa vào lớp nội bộ hoặc cơ chế lỗi thời.

## 2. `asSpreader()` làm gì?

Hãy xét phương thức:

```java
public static int sum3(int a, int b, int c) {
    return a + b + c;
}
```

Handle được tìm bằng:

```java
MethodHandle target = MethodHandles.lookup().findStatic(
        Demo.class,
        "sum3",
        MethodType.methodType(
                int.class, int.class, int.class, int.class));
```

Trong đoạn minh họa này, `Demo` là lớp khai báo `sum3`; ví dụ đầy đủ bên dưới dùng `SpreaderDemo`. Vì đây là phương thức `static`, `target.type()` là:

```text
(int,int,int)int
```

Để gộp **hai tham số cuối** thành một tham số kiểu `int[]`, gọi:

```java
MethodHandle adapted = target.asSpreader(int[].class, 2);
System.out.println(adapted.type()); // (int,int[])int
```

Lời gọi giờ có dạng:

```java
int result = (int) adapted.invokeExact(10, new int[] {20, 30});
// sum3(10, 20, 30) -> 60
```

Luồng giá trị:

```text
Handle gốc:       sum3(int a, int b, int c)  -> int
                      ^        ^      ^
                      |        |      |
Lời gọi adapter:     10      int[] {20, 30}
                      |        |      |
                      +--------+------+
                              |
                              v
                        sum3(10,20,30)
                              |
                              v
                             60
```

`asSpreader()` **không sửa handle gốc**: `target.type()` tiếp tục là `(int,int,int)int`. Nó trả về một `MethodHandle` khác, có kiểu lời gọi mới và thực hiện thao tác phân phối mảng trước khi gọi đích.

Tên “spreader” mô tả điều xảy ra **khi adapter được gọi**: một mảng từ phía caller được trải thành nhiều đối số của handle đích.

## 3. Hai overload cần nắm

Các chữ ký công khai:

```java
MethodHandle asSpreader(Class<?> arrayType, int arrayLength);

MethodHandle asSpreader(
        int spreadArgPos, Class<?> arrayType, int arrayLength);
```

| Tham số | Ý nghĩa |
| --- | --- |
| `arrayType` | Kiểu **mảng** mà adapter nhận, ví dụ `int[].class`, `long[].class` hoặc `String[].class`. Đây là kiểu của cả mảng, không phải kiểu một phần tử. |
| `arrayLength` | **Số phần tử phải được trải** để lấp các vị trí tham số của handle đích. Đây là giá trị cấu hình của adapter, không phải lời yêu cầu Java tự đọc `array.length` để quyết định số tham số. |
| `spreadArgPos` | Vị trí bắt đầu của nhóm tham số sẽ được thay bằng mảng; chỉ cần khi muốn trải ở giữa hoặc đầu danh sách thay vì mặc định ở cuối. |

Overload hai tham số trải **`arrayLength` tham số cuối** trong danh sách tham số của handle đích. Overload ba tham số chọn một đoạn gồm `arrayLength` tham số bắt đầu ở `spreadArgPos`.

Ví dụ với `target` có kiểu `(int,int,int)int`:

| Adapter | Kiểu sau thích nghi | Cách gọi |
| --- | --- | --- |
| `target.asSpreader(int[].class, 3)` | `(int[])int` | `invokeExact(new int[]{1,2,3})` |
| `target.asSpreader(int[].class, 2)` | `(int,int[])int` | `invokeExact(1, new int[]{2,3})` |
| `target.asSpreader(0, int[].class, 2)` | `(int[],int)int` | `invokeExact(new int[]{1,2}, 3)` |
| `target.asSpreader(1, int[].class, 1)` | `(int,int[],int)int` | `invokeExact(1, new int[]{2}, 3)` |

Tất cả các dòng trong bảng đều mô tả **kiểu lời gọi**; nếu đặt lời gọi trực tiếp vào Java, phải yêu cầu đúng kiểu kết quả, chẳng hạn `int value = (int) handle.invokeExact(...);`. Gọi `invokeExact` như một statement bỏ kết quả sẽ yêu cầu kiểu trả về `void`, dẫn đến lỗi kiểu với handle trả `int`.

**Quy tắc tính kiểu:** Nhóm `arrayLength` tham số được thay bằng **một** tham số kiểu `arrayType`; các tham số khác vẫn giữ vị trí tương đối; kiểu trả về của handle gốc không đổi.

## 4. Ví dụ trải đoạn tham số ở giữa

Không phải lúc nào mảng cũng tương ứng với các tham số cuối. Giả sử phương thức đích có bốn tham số:

```java
public static String surround(
        String prefix, String left, String right, String suffix) {
    return prefix + left + "|" + right + suffix;
}
```

Handle gốc có kiểu:

```text
(String,String,String,String)String
```

Ta muốn phía caller chỉ truyền ba đối số: `prefix`, mảng chứa `left` và `right`, `suffix`. Dùng overload có `spreadArgPos = 1`:

```java
MethodHandle middle = original.asSpreader(1, String[].class, 2);
System.out.println(middle.type());
// (String,String[],String)String

String text = (String) middle.invokeExact(
        "(", new String[] {"A", "B"}, ")");
// (A|B)
```

Vị trí `1` là chỉ số **bắt đầu của nhóm tham số trong handle gốc**, tính từ `0`: `prefix` là `0`, `left` là `1`, `right` là `2`, `suffix` là `3`.

Đây là tình huống điển hình ở adapter của formatter, router hoặc hệ thống dispatch: giữ lại các tham số bối cảnh (`prefix`, `suffix`) và chuyển một nhóm giá trị được lưu dưới dạng mảng vào đoạn tham số ở giữa.

## 5. Chọn kiểu mảng và cách chuyển phần tử

`arrayType` bắt buộc phải là một **kiểu mảng**. Với target nhận hai `int`, `int[].class` là lựa chọn trực quan nhất:

```java
MethodHandle spread = target.asSpreader(int[].class, 2);
```

Khi gọi `spread`, mỗi phần tử của `int[]` được đưa vào một tham số `int` tương ứng của target. Nếu nhóm tham số có kiểu khác với kiểu phần tử mảng, JDK chỉ có thể tạo adapter khi **chuyển đổi kiểu mà hợp đồng `MethodHandle` cho phép** là phù hợp; không nên giả định có thể tùy ý đổi giữa kiểu reference và primitive.

Một số tình huống:

- **Mảng primitive:** `int[]` chứa các phần tử `int`; khi dùng `invokeExact` với adapter kiểu `(int[])int`, điểm gọi nhận trực tiếp `int[]`. Không cần đóng gói mỗi phần tử thành một `Integer` ở API của caller.
- **Mảng reference:** `String[]` có thể cung cấp các tham số `String` của target. Các phép kiểm tra và chuyển đổi reference vẫn theo hợp đồng kiểu của method handles.
- **Mảng khác kiểu tại điểm gọi:** Nếu adapter có tham số `int[]` nhưng caller truyền `long[]` bằng `invokeExact`, kiểu điểm gọi không khớp. `invokeExact` không tự tạo `int[]` từ `long[]`.
- **Dữ liệu dạng `Object[]`:** Đừng mặc định `Object[]` tương đương `int[]`; cần xét phương thức chuyển đổi mà adapter hỗ trợ hoặc chuẩn hóa dữ liệu trước khi tạo mảng có kiểu đúng.
- **Đối số `null`:** Với adapter cần trải số phần tử dương, một tham chiếu mảng `null` không thể cung cấp các phần tử; cần kiểm tra dữ liệu trước khi gọi.

Trong mã ứng dụng, hãy chọn `arrayType` theo định dạng dữ liệu đầu vào thực tế và kiểu mà handle đích yêu cầu. Nếu cần xử lý một danh sách `List<?>` chứa giá trị `Object` động, `invokeWithArguments(List<?>)` có thể dễ đọc hơn; khi đó hợp đồng chuyển đổi lại thuộc API tương ứng.

## 6. `arrayLength` là một phần của hợp đồng, không tự biến đổi theo mảng

`arrayLength` cho biết adapter sẽ trải **chính xác bao nhiêu phần tử**. Ví dụ:

```java
MethodHandle spreadTwo = target.asSpreader(int[].class, 2);
// target: (int,int,int)int
// spreadTwo: (int,int[])int

int ok = (int) spreadTwo.invokeExact(10, new int[] {20, 30});
```

Nếu truyền mảng chỉ có một phần tử hoặc ba phần tử, số phần tử không khớp với `arrayLength = 2`. Với adapter kiểu này, việc gọi sẽ báo **`IllegalArgumentException`** do độ dài mảng sai:

```java
int invalid = (int) spreadTwo.invokeExact(10, new int[] {20});
// IllegalArgumentException: độ dài mảng không đúng yêu cầu.
```

Ngoài ra, nếu truyền `null` làm mảng khi phải trải hai phần tử, thao tác không thể đọc phần tử và phát sinh `NullPointerException`.

Các lỗi cần phân biệt:

| Giai đoạn | Tình huống | Dấu hiệu |
| --- | --- | --- |
| **Tạo adapter** | `arrayType` không phải kiểu mảng; `arrayLength` hoặc vị trí trải không hợp lệ; nhóm tham số không thích nghi được. | Thường là `IllegalArgumentException` hoặc `WrongMethodTypeException` theo điều kiện API cụ thể. |
| **Điểm gọi `invokeExact`** | Caller truyền `String[]` trong khi adapter yêu cầu `int[]`, hoặc bỏ mất một tham số còn lại. | `WrongMethodTypeException` vì chữ ký điểm gọi sai. |
| **Lúc adapter đọc mảng** | Mảng có độ dài khác `arrayLength`. | `IllegalArgumentException`. |
| **Lúc adapter đọc mảng** | Mảng `null` khi cần trải phần tử. | `NullPointerException`. |
| **Phép gọi đích** | Chính phương thức đích ném ngoại lệ. | Ngoại lệ đích được truyền tới caller theo hợp đồng `MethodHandle`. |

**Lưu ý:** `MethodHandle` và adapter không tự mở quyền tới một method/field. Việc tìm handle bằng `MethodHandles.Lookup` vẫn phải tuân theo quy tắc truy cập Java và JPMS; `asSpreader()` chỉ thay **hình dạng tham số của handle**, không thay quyền truy cập.

## 7. Ví dụ Java hoàn chỉnh, có thể chạy độc lập

Lưu file `SpreaderDemo.java` ở thư mục thực hành:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public final class SpreaderDemo {

    public static int sum3(int a, int b, int c) {
        return a + b + c;
    }

    public static String surround(
            String prefix, String left, String right, String suffix) {
        return prefix + left + "|" + right + suffix;
    }

    public static void main(String[] args) throws Throwable {
        System.out.println("JDK: " + Runtime.version());

        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle target = lookup.findStatic(
                SpreaderDemo.class,
                "sum3",
                MethodType.methodType(
                        int.class, int.class, int.class, int.class));

        System.out.println("target: " + target.type());
        // (int,int,int)int

        MethodHandle lastTwo = target.asSpreader(int[].class, 2);
        System.out.println("lastTwo: " + lastTwo.type());
        // (int,int[])int
        int firstResult = (int) lastTwo.invokeExact(
                10, new int[] {20, 30});
        System.out.println("lastTwo result: " + firstResult); // 60

        MethodHandle allThree = target.asSpreader(int[].class, 3);
        System.out.println("allThree: " + allThree.type());
        // (int[])int
        int secondResult = (int) allThree.invokeExact(
                new int[] {1, 2, 3});
        System.out.println("allThree result: " + secondResult); // 6

        MethodHandle firstTwo = target.asSpreader(
                0, int[].class, 2);
        System.out.println("firstTwo: " + firstTwo.type());
        // (int[],int)int
        int thirdResult = (int) firstTwo.invokeExact(
                new int[] {1, 2}, 3);
        System.out.println("firstTwo result: " + thirdResult); // 6

        MethodHandle text = lookup.findStatic(
                SpreaderDemo.class,
                "surround",
                MethodType.methodType(
                        String.class, String.class, String.class,
                        String.class, String.class));

        MethodHandle middle = text.asSpreader(
                1, String[].class, 2);
        System.out.println("middle: " + middle.type());
        // (String,String[],String)String
        String formatted = (String) middle.invokeExact(
                "(", new String[] {"A", "B"}, ")");
        System.out.println("middle result: " + formatted); // (A|B)

        System.out.println("original target: " + target.type());
        // Vẫn là (int,int,int)int

        try {
            int unused = (int) lastTwo.invokeExact(
                    10, new int[] {20});
            throw new AssertionError("Expected IllegalArgumentException: "
                    + unused);
        } catch (IllegalArgumentException expected) {
            System.out.println("wrong array length: "
                    + expected.getClass().getSimpleName());
        }

        try {
            int unused = (int) lastTwo.invokeExact(
                    10, (int[]) null);
            throw new AssertionError("Expected NullPointerException: "
                    + unused);
        } catch (NullPointerException expected) {
            System.out.println("null array: "
                    + expected.getClass().getSimpleName());
        }

        try {
            int unused = (int) lastTwo.invokeExact(
                    10, new long[] {20L, 30L});
            throw new AssertionError("Expected WrongMethodTypeException: "
                    + unused);
        } catch (WrongMethodTypeException expected) {
            System.out.println("wrong call-site type: "
                    + expected.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy trên **chính JDK cần kiểm chứng**:

```shell
java -version
javac -version
javac -encoding UTF-8 SpreaderDemo.java
java SpreaderDemo
```

Những dòng đầu ra dự kiến:

```text
target: (int,int,int)int
lastTwo: (int,int[])int
lastTwo result: 60
allThree: (int[])int
allThree result: 6
firstTwo: (int[],int)int
firstTwo result: 6
middle: (String,String[],String)String
middle result: (A|B)
original target: (int,int,int)int
wrong array length: IllegalArgumentException
null array: NullPointerException
wrong call-site type: WrongMethodTypeException
```

Chương trình in thêm thông tin `JDK: ...` trước các dòng trên. Thông báo và stack trace của ngoại lệ có thể khác giữa các phiên bản JDK; khi viết test, ưu tiên khẳng định **loại ngoại lệ** và `MethodType` thay vì cố định toàn bộ chuỗi thông báo.

Trong ví dụ này, `lookup` tìm các phương thức `public static` của chính lớp `SpreaderDemo`, giúp tập trung vào adapter. Nếu dùng method ở module khác, phải kiểm tra quyền truy cập của `Lookup` khi tạo handle trước khi xem xét `asSpreader()`.

## 8. `asSpreader()` khác gì `asCollector()`?

Hai adapter thao tác theo **hai hướng đối số ngược nhau**:

```text
asSpreader:
  phía caller:   (int[])
                         |
                         v
  handle đích:   (int, int)

asCollector:
  phía caller:   (int, int)
                         |
                         v
  handle đích:   (int[])
```

| Adapter | Hình dạng đầu vào của **handle gốc** | Hình dạng đầu vào sau adapter | Trường hợp phù hợp |
| --- | --- | --- | --- |
| `asSpreader(int[].class, 2)` | Hai tham số `int` riêng biệt. | Một tham số `int[]`. | Dữ liệu caller đã có mảng, đích nhận đối số rời. |
| `asCollector(int[].class, 2)` | Một tham số `int[]`. | Hai tham số `int` riêng biệt. | Caller muốn truyền đối số rời, đích xử lý mảng. |

Ví dụ minh họa hướng ngược:

```java
public static int sumArray(int[] values) {
    return values[0] + values[1];
}
```

Nếu `arrayTarget` có kiểu `(int[])int`, thì:

```java
MethodHandle twoInts = arrayTarget.asCollector(int[].class, 2);
// twoInts.type() == (int,int)int
```

`asSpreader()` **không phải** alias của `asCollector()`. Cũng không nên xem hai phép biến đổi là phép nghịch đảo bảo đảm giữ nguyên mọi hành vi trong mọi tình huống: cần xét kiểu phần tử, chuyển đổi, số lượng tham số và cách handle gốc được tạo.

## 9. So sánh với `invokeWithArguments()` và lời gọi bình thường

Giả sử có `target` kiểu `(int,int,int)int`:

```java
int direct = (int) target.invokeExact(1, 2, 3);

MethodHandle spread = target.asSpreader(int[].class, 3);
int viaArray = (int) spread.invokeExact(new int[] {1, 2, 3});

Object viaObjects = target.invokeWithArguments(1, 2, 3);
```

Sự khác nhau nằm ở **hợp đồng đối số được đưa đến điểm gọi**:

| Cách gọi | Đầu vào ở caller | Kiểu kết quả ở caller | Điểm quan trọng |
| --- | --- | --- | --- |
| `target.invokeExact(1,2,3)` | Ba `int` riêng lẻ. | `int` theo chữ ký đúng. | Khớp chính xác `MethodType` của target. |
| `spread.invokeExact(int[])` | Một `int[]` có số phần tử yêu cầu. | `int` theo chữ ký của adapter. | Trải mảng có kiểu rõ ràng trước khi gọi target. |
| `target.invokeWithArguments(1,2,3)` | Các giá trị qua giao diện `Object...`. | `Object` (kết quả `int` được boxing thành `Integer`). | Tiện cho bộ điều phối động nhưng có chuyển đổi và cách kiểm tra kiểu khác. |

Đừng nhầm rằng `invokeWithArguments(new int[]{1,2,3})` tương đương với `spread.invokeExact(new int[]{1,2,3})`. Với target nhận ba `int`, một `int[]` chỉ là **một đối số kiểu mảng**, còn target vẫn đòi ba tham số riêng. Adapter `asSpreader()` làm công việc phân phối mảng mà giao diện `invokeWithArguments` thông thường không tự thực hiện theo cách đó.

### Hiệu năng và mục đích sử dụng

`asSpreader()` thường phù hợp khi kiểu mảng và số phần tử đã biết, đặc biệt nếu một handle được tạo **một lần** rồi gọi nhiều lần. Nó làm rõ chữ ký tại điểm gọi và có thể tránh việc đưa từng phần tử primitive qua một `Object[]` như trong giao diện đối số tổng quát.

Tuy nhiên, **không** khẳng định `asSpreader()` luôn nhanh hơn mọi cách gọi khác: JIT có thể tối ưu nhiều bước, và hiệu năng còn phụ thuộc vào bản thân thao tác đích, độ ổn định call site, phân bổ mảng, mức warmup và phiên bản JDK. Nếu tốc độ là yêu cầu thiết kế, hãy đo bằng JMH và dữ liệu tương tự workload thực tế.

## 10. Một số lỗi thiết kế thường gặp

| Lỗi | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Gọi `asSpreader(int.class, 2)` | `int.class` là kiểu primitive, không phải **kiểu mảng**. | Dùng `int[].class`. |
| Gọi `asSpreader(int[].class, 2)` trên handle không có đủ tham số để trải | Cấu hình `arrayLength` không phù hợp với số vị trí tham số. | In `target.type()` và chọn số phần tử phù hợp. |
| Dùng sai `spreadArgPos` | Chọn sai vị trí bắt đầu của nhóm tham số ở handle gốc. | Đánh số tham số từ `0` rồi in `adapter.type()`. |
| Truyền mảng độ dài khác số đã khai báo | `arrayLength` là số phần tử **bắt buộc**, không tự co giãn. | Kiểm tra `array.length` trước khi gọi hoặc tạo adapter phù hợp. |
| Dùng `invokeExact` với `Object[]` khi handle yêu cầu `int[]` | Sai kiểu tham số tại điểm gọi. | Chuẩn hóa sang đúng kiểu mảng hoặc thiết kế lại adapter. |
| Gọi `invokeExact` nhưng không nhận kết quả của handle trả `int` | Call site bị coi là có kiểu trả về `void`. | Ép/nhận kết quả `int` trong biểu thức. |
| Nghĩ rằng adapter cấp quyền truy cập đến member private | `asSpreader()` chỉ đổi chữ ký gọi. | Lấy handle qua `Lookup` hợp lệ và tuân theo `exports`/`opens`. |

Các lỗi triển khai ở adapter và ở method đích có thể gây các loại ngoại lệ khác nhau. Khi chẩn đoán, hãy luôn ghi cả `target.type()`, `adapter.type()`, giá trị `arrayLength`, kiểu thực tế của mảng và lệnh gọi gây lỗi.

## 11. Bài tập thực hành

1. Chạy `SpreaderDemo.java` trên JDK đang sử dụng, ghi lại `java -version`, kiểu của `target`, `lastTwo`, `allThree`, `firstTwo` và `middle`.
2. Tạo adapter `target.asSpreader(1, int[].class, 1)`, dự đoán `MethodType`, sau đó gọi với `new int[]{2}` để tính `sum3(1,2,3)`.
3. Thay `arrayLength = 2` bằng `3` trong adapter trailing của `sum3`, kiểm tra vì sao chữ ký trở thành `(int[])int`.
4. Truyền mảng ngắn hơn và dài hơn độ dài bắt buộc, bắt riêng `IllegalArgumentException`. Thử `null` cho adapter có `arrayLength > 0` và quan sát `NullPointerException`.
5. Đổi một lời gọi `invokeExact` từ `int[]` sang `long[]` và giải thích lỗi bằng kiểu của **adapter**, không dựa vào giá trị số có thể vừa với `int`.
6. Viết `sumArray(int[])int`, dùng `asCollector(int[].class, 2)` và so sánh hướng chuyển tham số với `asSpreader()`.
7. Mô tả một bộ dispatch nhận dữ liệu `List<?>`. Giải thích khi nào nên chuẩn hóa dữ liệu thành `int[]` rồi gọi spreader và khi nào nên dùng `invokeWithArguments(List<?>)`.

### Câu hỏi tự kiểm tra

**Câu 1:** `asSpreader()` có đổi chữ ký của handle gốc không?

**Trả lời:** Không. Nó tạo một `MethodHandle` mới với chữ ký nhận tham số mảng; handle gốc giữ nguyên kiểu và thao tác.

**Câu 2:** Với `target.type() == (int,int,int)int`, `target.asSpreader(int[].class,2).type()` là gì?

**Trả lời:** `(int,int[])int`. Hai tham số cuối `int` được thay bằng một tham số `int[]`.

**Câu 3:** `arrayLength = 2` có chấp nhận mảng dài ba phần tử rồi tự bỏ phần tử dư không?

**Trả lời:** Không. Adapter yêu cầu số phần tử đúng với cấu hình, và mảng sai độ dài gây `IllegalArgumentException`.

**Câu 4:** Có thể gọi `asSpreader(1, String[].class,2)` để trải các tham số ở giữa không?

**Trả lời:** Có, nếu nhóm tham số bắt đầu ở vị trí `1` và chuyển đổi từ phần tử `String[]` sang các tham số mục tiêu là hợp lệ.

**Câu 5:** Lợi ích chính so với `invokeWithArguments()` là gì?

**Trả lời:** Adapter tạo ra chữ ký có kiểu mảng rõ ràng để caller có thể dùng `invokeExact` mà vẫn phân phối mảng cho một nhóm tham số của target. `invokeWithArguments` phù hợp hơn khi dữ liệu đầu vào được biểu diễn động qua `Object...` hoặc `List<?>`.

## 12. Tài liệu tham khảo

- Java SE API — `MethodHandle.asSpreader`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandle.html
- Java SE API — `MethodType`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodType.html
- Java SE API — `MethodHandles.Lookup`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- OpenJDK JEP 416 — *Reimplement Core Reflection with Method Handles*: https://openjdk.org/jeps/416

Khi xác minh hợp đồng `asSpreader()`, hãy đọc Javadoc **đúng phiên bản JDK đang chạy**, nhất là các chi tiết về chuyển đổi kiểu phần tử, giới hạn đối số và ngoại lệ.
