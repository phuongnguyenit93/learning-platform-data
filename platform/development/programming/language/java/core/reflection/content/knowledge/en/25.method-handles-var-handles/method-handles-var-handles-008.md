# VarHandle cho field hoặc phần tử mảng trong Java

## 1. VarHandle giải quyết vấn đề gì?

Khi làm việc với Java Reflection, ta có thể lấy và sửa giá trị của field thông qua `java.lang.reflect.Field`. Với code đồng thời (concurrency), ta còn cần chỉ định **cách đọc/ghi bộ nhớ** và đôi khi phải thực hiện các thao tác **nguyên tử** như tăng biến đếm hoặc đổi giá trị nếu nó vẫn bằng giá trị mong đợi. Từ Java 9, `java.lang.invoke.VarHandle` cung cấp một cách truy cập biến có kiểu rõ ràng và nhiều chế độ truy cập (access mode).

Một `VarHandle` đại diện cho **vị trí lưu biến**: một instance field, static field, phần tử mảng hoặc dạng view trên vùng nhớ được các factory tương ứng hỗ trợ. Bài này tập trung vào **field và phần tử mảng**. Khác với `MethodHandle` đại diện cho thao tác gọi, `VarHandle` đại diện cho **biến được truy cập** cùng tập thao tác hợp lệ trên biến đó.

Điểm cần phân biệt:

- **Biến nào?** Một field cụ thể hoặc một phần tử của một loại mảng.
- **Định vị biến ra sao?** Instance field cần đối tượng receiver; static field không cần receiver; phần tử mảng cần đối tượng mảng và chỉ số.
- **Thao tác nào?** Đọc/ghi thường (`get`/`set`), đọc/ghi với quy tắc memory ordering (`getVolatile`/`setVolatile`, `getAcquire`/`setRelease`, v.v.), hoặc thao tác nguyên tử như `compareAndSet` và `getAndAdd`.
- **Có quyền hay không?** Tra cứu field vẫn tuân thủ kiểm soát truy cập Java/module. Có handle không phải giấy phép sửa mọi field: access mode không được hỗ trợ vẫn có thể bị từ chối.

## 2. Mô hình variable type và coordinate types

Một `VarHandle` có hai thông tin đặc trưng:

1. `varType()`: kiểu dữ liệu của biến được truy cập, ví dụ `int.class`, `String.class`.
2. `coordinateTypes()`: danh sách kiểu để **xác định vị trí** của biến. Đây không phải danh sách tham số của phương thức Java thông thường.

| Vị trí biến | Cách lấy handle | `varType()` | `coordinateTypes()` | Ví dụ đọc |
| --- | --- | --- | --- | --- |
| Instance field `Counter.value: int` | `lookup.findVarHandle(Counter.class, "value", int.class)` | `int` | `[Counter]` | `(int) vh.get(counter)` |
| Static field `Config.level: int` | `lookup.findStaticVarHandle(Config.class, "level", int.class)` | `int` | `[]` | `(int) vh.get()` |
| Phần tử `int[]` | `MethodHandles.arrayElementVarHandle(int[].class)` | `int` | `[int[], int]` | `(int) vh.get(numbers, index)` |

Các lời gọi bên phải được minh họa dưới giả định `vh` là handle phù hợp với dòng tương ứng. Với `arrayElementVarHandle`, handle đại diện cho **cách truy cập phần tử của loại mảng**, chưa gắn với một mảng hoặc một vị trí cố định nào: truyền mảng và index vào mỗi lần gọi.

Cách xác định đối số cho một access mode:

```text
instance field:  get(receiver)                     set(receiver, value)
static field:    get()                             set(value)
array element:   get(array, index)                 set(array, index, value)

compareAndSet:   compareAndSet(coordinates..., expected, update)
getAndAdd:       getAndAdd(coordinates..., delta)
```

`coordinates...` là toàn bộ tọa độ phù hợp với loại handle. Với `get`, kết quả có kiểu `varType`; với `set`, lời gọi không có kết quả; với `compareAndSet`, kết quả kiểu `boolean`; với `getAndAdd`, kết quả là giá trị **trước** khi cộng.

## 3. Tạo VarHandle cho instance field

Dùng `MethodHandles.Lookup.findVarHandle`:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
VarHandle valueHandle = lookup.findVarHandle(
    Counter.class,
    "value",
    int.class
);
```

Trong ví dụ này, `Counter` có field instance tên `value` kiểu `int`. Field **không** phải static. Khi tra cứu, loại `int.class` phải khớp kiểu khai báo của field; khi truy cập, cần receiver là một `Counter` hợp lệ.

Nếu field khai báo `private`, lookup phải có quyền private tương ứng. `MethodHandles.lookup()` được gắn với lớp nơi nó được gọi; việc di chuyển mã lookup sang lớp khác có thể làm thay đổi quyền. `MethodHandles.publicLookup()` không tự cung cấp quyền private. Các quy tắc package và Java module cũng áp dụng; `privateLookupIn` chỉ hoạt động khi thỏa điều kiện truy cập cần thiết.

Ví dụ thao tác trên cùng một handle:

```java
valueHandle.set(counter, 10);                            // Ghi plain.
int current = (int) valueHandle.get(counter);             // Đọc plain.
int old = (int) valueHandle.getAndAdd(counter, 5);        // Cộng nguyên tử, trả giá trị cũ.
boolean changed = (boolean) valueHandle.compareAndSet(
    counter, 15, 20                                      // Chỉ đổi 15 -> 20 nếu còn là 15.
);
```

Đây là **đoạn mã minh họa**, dùng biến `valueHandle` và `counter` đã tạo ở nơi khác; chương trình độc lập chạy được nằm ở mục 7. Lưu ý `get` và `set` là plain access, không nên dựa vào chúng thay cho quy tắc đồng bộ giữa các thread.

## 4. VarHandle cho static field

Với field `static`, phải dùng `findStaticVarHandle`:

```java
VarHandle sharedHandle = lookup.findStaticVarHandle(
    Config.class,
    "level",
    int.class
);

sharedHandle.setVolatile(7);
int level = (int) sharedHandle.getVolatile();
```

Dòng đầu giả định `Config` có static field `level` kiểu `int` và lookup có quyền truy cập; đoạn này minh họa trong ngữ cảnh có biến `lookup`. Khác với instance field, `sharedHandle.coordinateTypes()` rỗng, nên **không** truyền đối tượng `Config` vào `getVolatile` hoặc `setVolatile`.

Không tráo `findVarHandle` với `findStaticVarHandle`: hai API tra cứu hai loại field khác nhau. Tên field, lớp khai báo và kiểu field phải đúng. Đây là khác biệt về **định vị biến**, còn các access mode được hỗ trợ vẫn phụ thuộc loại field và kiểu giá trị.

## 5. VarHandle cho phần tử mảng

Dùng factory:

```java
VarHandle elementHandle = MethodHandles.arrayElementVarHandle(int[].class);
int[] scores = {10, 20, 30};

int first = (int) elementHandle.get(scores, 0);      // 10
elementHandle.set(scores, 1, 25);                    // scores[1] = 25
int old = (int) elementHandle.getAndAdd(scores, 2, 5); // old = 30; scores[2] = 35
```

Đoạn này là minh họa độc lập về cú pháp khi được đặt trong method có import tương ứng. Một handle được tạo từ `int[].class` có thể làm việc với nhiều đối tượng `int[]` khác nhau; mỗi lần gọi đều cần truyền **mảng** và **chỉ số**.

Các lưu ý:

- `arrayElementVarHandle` nhận **loại mảng**, ví dụ `int[].class` hoặc `String[].class`, không nhận một instance mảng làm tham số factory.
- Với mảng `int[]`, `varType()` là `int.class`; `coordinateTypes()` chứa kiểu mảng `int[].class` và `int.class` cho chỉ số.
- Một index ngoài giới hạn sẽ gây `ArrayIndexOutOfBoundsException`; receiver mảng `null` gây `NullPointerException`.
- Những phép toán như `getAndAdd` chỉ có ý nghĩa trên kiểu dữ liệu được access mode đó hỗ trợ. Không mặc định áp dụng phép cộng cho `String[]`.
- Nếu là mảng tham chiếu, quy tắc tương thích kiểu phần tử của Java vẫn có hiệu lực, kể cả kiểm tra lưu phần tử vào mảng thực tế.

## 6. Định vị biến khác với chọn access mode
Khi đã tạo `VarHandle` cho đúng vị trí, mỗi phép toán còn có **quy tắc truy cập** riêng. `get`/`set` có ngữ nghĩa plain, `getVolatile`/`setVolatile` có ngữ nghĩa volatile, `getAcquire`/`setRelease` dùng trong giao thức publish/consume, còn `compareAndSet` và `getAndAdd` là các phép cập nhật nguyên tử khi được hỗ trợ. Phải dùng `isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD)` nếu công cụ xử lý động không biết trước kiểu biến.

Hai phép `get` rồi `set` vẫn là hai thao tác rời, vì vậy không thay thế `getAndAdd` khi nhiều luồng cùng tăng biến. Tương tự, `get` hoặc `set` plain không đủ để tự tạo quan hệ happens-before giữa các luồng. Khi nghiên cứu đồng thời, phải xác định đúng access mode và giao thức chia sẻ dữ liệu; bài về memory ordering trong cùng chương phân tích các điều kiện này đầy đủ hơn.

## 7. Chương trình đầy đủ: instance field, static field và mảng

Lưu toàn bộ code dưới đây thành `VarHandleDemo.java`, sử dụng JDK 17+.

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.util.Arrays;

public class VarHandleDemo {
    private static class Counter {
        private volatile int value;
    }

    private static volatile int shared;

    public static void main(String[] args) throws ReflectiveOperationException {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        VarHandle field = lookup.findVarHandle(Counter.class, "value", int.class);
        VarHandle staticField = lookup.findStaticVarHandle(
            VarHandleDemo.class, "shared", int.class
        );
        VarHandle element = MethodHandles.arrayElementVarHandle(int[].class);

        Counter counter = new Counter();
        field.setVolatile(counter, 10);
        System.out.println("field initial = " + (int) field.getVolatile(counter));
        System.out.println("field old = " + (int) field.getAndAdd(counter, 5));
        System.out.println("field CAS = "
                + (boolean) field.compareAndSet(counter, 15, 21));
        System.out.println("field final = " + (int) field.getVolatile(counter));

        staticField.setVolatile(7);
        System.out.println("static = " + (int) staticField.getVolatile());

        int[] numbers = {3, 4, 5};
        element.set(numbers, 1, 40);
        System.out.println("array old = " + (int) element.getAndAdd(numbers, 1, 2));
        System.out.println("array CAS = "
                + (boolean) element.compareAndSet(numbers, 2, 5, 50));
        System.out.println("array = " + Arrays.toString(numbers));

        System.out.println("field coordinates = " + field.coordinateTypes().size());
        System.out.println("static coordinates = " + staticField.coordinateTypes().size());
        System.out.println("array coordinates = " + element.coordinateTypes().size());
        System.out.println("variable type = " + field.varType().getSimpleName());
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```bash
javac -encoding UTF-8 VarHandleDemo.java
java VarHandleDemo
```

**Đầu ra xác định** (đã được kiểm tra trên JDK 21):

```text
field initial = 10
field old = 10
field CAS = true
field final = 21
static = 7
array old = 40
array CAS = true
array = [3, 42, 50]
field coordinates = 1
static coordinates = 0
array coordinates = 2
variable type = int
```

Phân tích từng nhóm:

1. `field.setVolatile(counter, 10)` đặt giá trị ban đầu. `getAndAdd(counter, 5)` trả về **10** rồi biến đổi giá trị thành **15**; `compareAndSet(counter, 15, 21)` thành công và đưa giá trị thành **21**.
2. `staticField` không cần truyền receiver: `setVolatile(7)` và `getVolatile()` truy cập trực tiếp field static.
3. `element.set(numbers, 1, 40)` chỉnh phần tử thứ hai. `getAndAdd(numbers, 1, 2)` trả **40** và cập nhật phần tử thành **42**. CAS đổi phần tử index 2 từ **5** sang **50**.
4. Ba kết quả tọa độ lần lượt là **1**, **0**, **2**, đúng với instance field, static field, array element; tất cả đều có `varType` là `int` trong ví dụ.

Lớp `Counter` là lớp lồng nhau của `VarHandleDemo` và cả hai cùng *nest*, vì vậy lookup trong lớp ngoài có quyền truy cập field private của `Counter`. Khi chuyển code sang những lớp/module khác, cần xét lại quyền truy cập thay vì sao chép nguyên cú pháp lookup rồi giả định kết quả vẫn thành công.

## 8. Lỗi phổ biến và cách chẩn đoán

| Lỗi / triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| `NoSuchFieldException` khi tìm | Sai tên field, kiểu khai báo hoặc lựa chọn instance/static | Xem field thực tế, phân biệt `findVarHandle` với `findStaticVarHandle` |
| `IllegalAccessException` khi tìm | Lookup không có quyền tới field hoặc module/package | Tạo lookup ở lớp có quyền thích hợp; xem modifier và `exports`/`opens`; không tùy tiện mở module |
| `WrongMethodTypeException` lúc gọi | Thiếu receiver, thiếu index, sai kiểu dữ liệu hoặc kiểu kết quả tại chỗ gọi | Kiểm tra `varType()`, `coordinateTypes()` và cast kết quả |
| `ClassCastException` hoặc lỗi runtime khác | Đối tượng receiver hoặc giá trị runtime không tương thích | Kiểm tra kiểu đối tượng và kiểu biến thực tế |
| `ArrayIndexOutOfBoundsException` / `NullPointerException` | Index không hợp lệ / mảng hoặc receiver null | Kiểm tra mảng, receiver và index trước khi gọi |
| `UnsupportedOperationException` | Mode không hỗ trợ, ví dụ ghi qua handle của field `final` hoặc arithmetic trên kiểu không thích hợp | Dùng `isAccessModeSupported(...)`; chọn mode/kiểu dữ liệu khác |
| Đếm sai khi nhiều thread cập nhật | Dùng cặp `get` rồi `set` dẫn tới lost update | Dùng thao tác nguyên tử như `getAndAdd` hoặc giải pháp đồng bộ phù hợp |
| Hiểu nhầm dữ liệu giữa các thread | Dùng plain access mà mong hiệu ứng volatile | Chọn access mode và giao thức đồng bộ đúng Java Memory Model |

Đừng dùng `VarHandle` như cách bỏ qua mọi quy tắc truy cập. Nó cung cấp cơ chế thao tác biến động và memory ordering, nhưng không miễn trừ quyền Java, kiểu dữ liệu, hay tính đúng đắn của thuật toán đồng thời.

## 9. Bài luyện tập

1. Viết class `Book` chứa `private int copies`. Tạo `VarHandle` hợp lệ cho field, đọc và cập nhật số bản sao. Nêu `coordinateTypes()` của handle.
2. Tạo `String[] names` và handle cho phần tử mảng. Vì sao `getAndAdd(names, 0, ...)` không phải thao tác phù hợp?
3. Nếu `Config.active` là `static boolean`, cần dùng factory nào, và số coordinate là bao nhiêu?
4. Hai thread cùng chạy `x = get(x) + 1; set(x)` thì vì sao kết quả cuối có thể nhỏ hơn tổng số lần tăng? Thay bằng API nào?
5. Với `compareAndSet`, xác định expected/update và giải thích giá trị trả về. Nếu field là `final`, thao tác nào phải tránh?
6. Thử dùng `isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD)` với một handle có kiểu biến không hỗ trợ phép cộng, rồi giải thích kết quả.

**Mục tiêu hoàn thành:** người học xác định được kiểu biến và tọa độ cho instance/static field và phần tử mảng; tạo đúng handle; gọi đúng `get`, `set`, `getAndAdd`, `compareAndSet`; chọn access mode theo yêu cầu đồng thời và nhận diện giới hạn truy cập.