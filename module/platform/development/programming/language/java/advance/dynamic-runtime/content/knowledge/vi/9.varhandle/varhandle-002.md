# 9.2 Tạo handle cho field static, instance và phần tử mảng

## 1. VarHandle là gì và vì sao cần phân biệt ba loại biến?

`java.lang.invoke.VarHandle` (có từ Java 9) là một đối tượng đại diện cho **quyền truy cập một biến có kiểu cụ thể**. Biến đó có thể là **field của một đối tượng**, **static field của một class**, hoặc **phần tử của một array**. Thay vì chỉ gọi `Field.get`/`Field.set` như Reflection truyền thống, ta tạo một VarHandle rồi dùng các access mode như `get`, `set`, `getVolatile`, `compareAndSet` hay `getAndAdd` khi kiểu biến và quyền truy cập hỗ trợ.

Trọng tâm của bài **9.2** là **cách tạo đúng handle và hiểu hình dạng tham số của nó**:

- `MethodHandles.Lookup.findVarHandle(...)`: tìm **instance field**.
- `MethodHandles.Lookup.findStaticVarHandle(...)`: tìm **static field**.
- `MethodHandles.arrayElementVarHandle(...)`: tạo handle truy cập **một phần tử của array**.
- `Lookup.unreflectVarHandle(Field)`: chuyển metadata `Field` đã biết thành VarHandle, vẫn phải tuân thủ quyền truy cập.

Sau bài này, bạn có thể nhận diện `varType()` và `coordinateTypes()`, gọi handle đúng số lượng/thứ tự tham số, hiểu sự khác biệt giữa kiểm tra quyền tại lúc tạo handle và truy cập giá trị tại lúc gọi, cũng như xử lý những lỗi phổ biến liên quan tới final field, sai tên/kiểu field, sai chỉ số mảng và ranh giới module.

> **Tư duy chính:** VarHandle xác định *biến cần thao tác* và *những tọa độ cần cung cấp để xác định một vị trí lưu trữ cụ thể*. Đối với instance field, tọa độ là **đối tượng chứa field**; đối với static field, **không có tọa độ**; đối với array element, tọa độ là **mảng và chỉ số**.

## 2. Hai khái niệm nền tảng: variable type và coordinate types

Một VarHandle được mô tả bằng hai phần độc lập:

1. **`varType()`**: kiểu của giá trị được lưu trong biến mà handle quản lý, ví dụ `int.class`, `long.class`, `String.class`. Đây **không** phải kiểu của đối tượng chứa field.
2. **`coordinateTypes()`**: danh sách `Class<?>` của những tham số phải cung cấp để định vị ô nhớ/biến. Thứ tự của danh sách này cũng là thứ tự khi gọi `get`/`set`.

Bảng so sánh:

| Loại biến | Cách tạo | Ví dụ `varType()` | Ví dụ `coordinateTypes()` | `get` | `set` |
| --- | --- | --- | --- | --- | --- |
| Instance field `State.count` kiểu `int` | `lookup.findVarHandle(State.class,"count",int.class)` | `int` | `[State]` | `(int) vh.get(state)` | `vh.set(state,5)` |
| Static field `State.total` kiểu `long` | `lookup.findStaticVarHandle(State.class,"total",long.class)` | `long` | `[]` | `(long) vh.get()` | `vh.set(200L)` |
| Array element kiểu `int` | `MethodHandles.arrayElementVarHandle(int[].class)` | `int` | `[int[],int]` | `(int) vh.get(numbers,1)` | `vh.set(numbers,1,25)` |

Cụm "tọa độ" ở đây không phải địa chỉ bộ nhớ thô. Đó là **các đối số Java có kiểu** mà VarHandle cần để biết vị trí lưu trữ.

Ví dụ, `State` có thể có hàng trăm instance. Handle `count` là cùng một đối tượng truy cập, còn `stateA` và `stateB` trong các lời gọi `countHandle.get(stateA)`/`get(stateB)` là hai tọa độ trỏ tới hai ô field của hai object khác nhau.

Ngược lại, `static` field là một biến gắn với class, không với từng instance: `get()` không nhận receiver. Cố truyền `state` vào `get(state)` của static VarHandle không có cùng chữ ký gọi hợp lệ.

Với array, cùng một handle `arrayElementVarHandle(int[].class)` dùng được cho **nhiều mảng `int[]`**, vì mỗi thao tác cung cấp array và chỉ số cụ thể; nó không cố định vĩnh viễn vào một mảng được truyền vào lúc tạo.

### 2.1. Method type của mỗi access mode

Các phương thức như `get` và `set` trên `VarHandle` là **signature-polymorphic**. Kiểu lời gọi phụ thuộc cả vào **coordinate types** và **varType**. Có thể hỏi handle:

```java
MethodType getType = vh.accessModeType(VarHandle.AccessMode.GET);
MethodType setType = vh.accessModeType(VarHandle.AccessMode.SET);
```

Nếu `vh` quản lý instance field `int count` của `State`, về mặt khái niệm:

```text
GET             (State)int
SET             (State,int)void
COMPARE_AND_SET (State,int,int)boolean
GET_AND_ADD     (State,int)int
```

Trong đó mỗi mode tiếp nhận **tọa độ trước**, sau đó mới đến **giá trị cần ghi / giá trị expected / delta**.

Với static field `long total`:

```text
GET  ()long
SET  (long)void
```

Với `int[]` element:

```text
GET (int[],int)int
SET (int[],int,int)void
```

Không nên tự dựng chữ ký dựa vào tên method `get`/`set` rồi đoán số lượng tham số. Hãy dựa vào `coordinateTypes()`, `varType()` và `accessModeType(...)` của handle thực tế.

## 3. Tạo VarHandle cho instance field bằng `findVarHandle`

### 3.1. Cú pháp và ý nghĩa các tham số

```java
VarHandle vh = lookup.findVarHandle(
        State.class,  // declaring/reference class chứa field
        "count",      // tên field (chuỗi)
        int.class);   // kiểu field phải khớp
```

`lookup` là một `MethodHandles.Lookup` mang **ngữ cảnh quyền truy cập**. Thông thường, mã bên trong class hoặc nest hợp lệ bắt đầu từ `MethodHandles.lookup()`. Factory trả về một VarHandle cho **field instance** `count`.

Lệnh trên **không đọc giá trị `count` ngay lập tức**. Nó tạo khả năng truy cập; khi gọi `vh.get(state)`, tọa độ `state` mới xác định biến của instance cụ thể.

Điều kiện thực tiễn:

- Class và tên field phải đúng; kiểu thứ ba phải là **kiểu field chính xác**, không phải kiểu của object chứa. Với field `int count`, dùng `int.class` chứ không dùng `Integer.class`.
- Field phải phù hợp với chế độ instance của factory và ngữ cảnh `Lookup` phải có quyền truy cập. Tên field, loại static/instance hoặc quyền truy cập sai sẽ làm **lookup không thành công**.
- `findVarHandle` có thể ném `NoSuchFieldException` hoặc `IllegalAccessException`; do đó phương thức chứa lệnh thường khai báo `throws ReflectiveOperationException`, hoặc xử lý các ngoại lệ kiểm tra này.
- Không cần tạo một VarHandle cho từng đối tượng `State`. Có thể giữ **một handle** và cung cấp receiver thích hợp ở mỗi lần `get`/`set`.

Ví dụ minh họa:

```java
State first = new State();
State second = new State();

int before = (int) countHandle.get(first);
countHandle.set(first, 10);
int other = (int) countHandle.get(second);
```

Đây là **trích đoạn**, không phải chương trình độc lập. Giả sử hai object khởi tạo `count=1`, thì `before=1`; chỉ `first` đổi thành 10, còn `other=1`. Hai lời gọi dùng cùng handle nhưng tọa độ khác nhau.

### 3.2. Instance field `private` và quyền của `Lookup`

Nếu `count` là `private`, không có nghĩa mọi `MethodHandles.lookup()` từ mọi class đều được phép tạo handle. Lookup có quyền dựa trên nơi gọi và module/package visibility. Đoạn mã hoàn chỉnh ở mục 6 đặt `State` là **nested class trong cùng top-level class**, để code của ví dụ có quyền truy cập private qua cơ chế nestmates của Java; không có mẹo vượt quyền.

Với private field của một class ở package/module khác, cần xem mục 8 về `privateLookupIn`, `module-info.java` và khả năng `opens`. Không dùng những phương thức tạo VarHandle như một công cụ tự động bỏ qua encapsulation.

### 3.3. Receiver phải là đúng object

Đối với instance field:

```java
int value = (int) countHandle.get(state);
countHandle.set(state, 5);
```

`state` cần phù hợp với kiểu receiver của VarHandle. Không truyền `State.class` thay cho một đối tượng `State`; cũng không bỏ receiver khi gọi `get()`. Đối với lời gọi signature-polymorphic, sai số lượng hoặc kiểu tham số có thể tạo `WrongMethodTypeException`, còn lỗi receiver null hoặc kiểm tra runtime khác có thể dẫn tới ngoại lệ khác. Không đánh đồng mọi lỗi với `IllegalAccessException`: lỗi quyền lookup xảy ra tại **giai đoạn tạo** và lỗi gọi xảy ra tại **giai đoạn sử dụng** là hai lớp vấn đề khác nhau.

## 4. Tạo VarHandle cho static field bằng `findStaticVarHandle`

Cú pháp:

```java
VarHandle totalHandle = lookup.findStaticVarHandle(
        State.class, "total", long.class);
```

Với field:

```java
private static volatile long total = 100L;
```

VarHandle sẽ có:

- `varType() = long.class`.
- `coordinateTypes() = []`, vì không có receiver hay array index.
- `(long) totalHandle.get()` đọc `total`.
- `totalHandle.set(200L)` ghi `total`.

Trước khi gọi, biến `total` thuộc class chứa field; đây không phải trường hợp một biến `total` trên từng `State`.

**Dễ nhầm:** `findStaticVarHandle` không tương đương `findVarHandle`. Nếu code lấy handle bằng factory sai so với loại field thực, lookup không thành công. Đừng thử sửa bằng cách tùy tiện thêm một đối số receiver khi gọi.

### 4.1. Static không có nghĩa là final

Một `static` field vẫn có thể thay đổi nếu nó không phải `final` và mode ghi phù hợp được hỗ trợ. Ngược lại, `static final` field thường có **VarHandle chỉ đọc**; không nên suy luận rằng đã tạo được handle thì chắc chắn gọi `set` được.

Trong ví dụ chính, `total` là `static volatile long` để minh họa cả thao tác thường và truy cập có yêu cầu đồng bộ trong ứng dụng thực tế. Trên VarHandle, **access mode** (`get`, `getVolatile`, `setVolatile`...) mới là điều xác định ý nghĩa truy cập tương ứng; từ khóa `volatile` của khai báo field **không tự biến mọi lời gọi `get` thành `getVolatile`** trong cách sử dụng API VarHandle.

### 4.2. Có thể dùng chung handle, không tạo lại mỗi lần đọc

Một ví dụ pattern trong module/class có quyền phù hợp:

```java
// Trích đoạn minh họa, không phải class đầy đủ.
private static final VarHandle TOTAL_HANDLE;

static {
    try {
        TOTAL_HANDLE = MethodHandles.lookup()
                .findStaticVarHandle(State.class, "total", long.class);
    } catch (ReflectiveOperationException ex) {
        throw new ExceptionInInitializerError(ex);
    }
}
```

Tạo handle một lần và cache nó giúp tránh lặp lại thao tác lookup trong code sử dụng nhiều lần. Chỉ áp dụng khi field tồn tại, class/mối quan hệ quyền truy cập được kiểm soát, và lỗi khởi tạo được xử lý phù hợp. Đây là **trích đoạn** giả định có `State` và `import` tương ứng.

## 5. Tạo VarHandle cho phần tử mảng bằng `arrayElementVarHandle`

Đây là factory khác về bản chất: **không cần truyền `Lookup` hay tên field**.

```java
VarHandle element = MethodHandles.arrayElementVarHandle(int[].class);
```

Nó quản lý **phần tử kiểu `int`** bên trong bất kỳ mảng `int[]` phù hợp. Kiểu mảng được đưa vào ngay lúc tạo, nhưng mảng **cụ thể** chỉ truyền vào khi sử dụng.

Ví dụ:

```java
int[] numbers = {10, 20, 30};
int middle = (int) element.get(numbers, 1);
element.set(numbers, 1, 25);
// middle == 20; numbers sau set: {10, 25, 30}
```

Tọa độ của array element handle là:

1. **Tham chiếu đến array**: `int[]`.
2. **Chỉ số `int`**: 0-based như truy cập mảng Java thông thường.

Sau đó, nếu access mode là `set`, đối số thứ ba là **giá trị phần tử cần ghi** (`int`).

### 5.1. Phân biệt kiểu mảng và kiểu phần tử

| Factory call | `varType()` | `coordinateTypes()` |
| --- | --- | --- |
| `arrayElementVarHandle(int[].class)` | `int.class` | `[int[].class, int.class]` |
| `arrayElementVarHandle(String[].class)` | `String.class` | `[String[].class, int.class]` |
| `arrayElementVarHandle(String[][].class)` | `String[].class` | `[String[][].class, int.class]` |
| `arrayElementVarHandle(Object[].class)` | `Object.class` | `[Object[].class, int.class]` |

Với mảng hai chiều `String[][]`, phần tử **cấp 1** là một `String[]`. Vì thế VarHandle do `arrayElementVarHandle(String[][].class)` tạo chỉ định vị một row bằng hai tọa độ: **mảng 2D + index hàng**. Nó **không tự sinh** handle nhận ba tọa độ `(matrix,row,column)`. Để đọc một phần tử `String` sâu hơn, hãy lấy hàng tương ứng trước rồi dùng một handle cho `String[].class` hoặc truy cập mảng bình thường.

Ví dụ khái niệm:

```java
// Trích đoạn, giả định import java.lang.invoke.*.
String[][] matrix = {{"A", "B"}, {"C", "D"}};
VarHandle rowHandle =
        MethodHandles.arrayElementVarHandle(String[][].class);
String[] row = (String[]) rowHandle.get(matrix, 1);
// row chứa ["C", "D"].
```

### 5.2. Không phải mọi đối tượng đều là array

`arrayElementVarHandle(String.class)` là lời gọi tạo handle **không hợp lệ** vì `String.class` không phải array class; factory yêu cầu `Class<?>` biểu diễn một kiểu mảng. Dùng `String[].class` nếu bạn muốn truy cập từng `String` trong array.

Nói cách khác, API không tạo handle cho `List<E>`, `Map<K,V>` hay một đối tượng tùy ý. Để thao tác `List`, dùng API của `List` hoặc method handle cho method của nó; VarHandle array-element chỉ dùng cho **array JVM**.

### 5.3. Các lỗi lúc sử dụng

- Mảng `null`: thao tác cần vị trí phần tử không có array hợp lệ và có thể ném `NullPointerException`.
- Chỉ số âm hoặc `index >= array.length`: `ArrayIndexOutOfBoundsException`.
- Chỉ số phải có kiểu phù hợp với tham số tọa độ `int`; không có cơ chế tra cứu bằng key như `Map`.
- Mảng kiểu khác `int[]` không thể dùng với handle có `coordinateTypes() = [int[],int]` chỉ vì các phần tử nhìn giống nhau. `int[]` và `Integer[]` là hai kiểu mảng khác biệt.
- Nếu thực hiện CAS hoặc các access mode khác, phải kiểm tra **mode được hỗ trợ cho kiểu phần tử**; không suy diễn mọi array element đều hỗ trợ mọi phép toán.

## 6. Ví dụ Java 17+ độc lập: tạo cả ba handle và kiểm tra metadata

Ví dụ này dùng một nested class `State` có instance field, static field, final field; sau đó tạo VarHandle cho `int[]`. Nó còn kiểm tra `unreflectVarHandle`, supported modes và các lỗi cố ý.

Tạo file **`VarHandleCreationDemo.java`** chứa đúng mã sau:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VarHandle;
import java.lang.invoke.WrongMethodTypeException;
import java.lang.reflect.Field;
import java.util.Arrays;

public class VarHandleCreationDemo {
    static final class State {
        private volatile int count = 1;
        private static volatile long total = 100L;
        private final String label = "fixed";
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        // Instance field: receiver State + varType int.
        VarHandle instance =
                lookup.findVarHandle(State.class, "count", int.class);

        // Static field: không có receiver; varType long.
        VarHandle global =
                lookup.findStaticVarHandle(State.class, "total", long.class);

        // Array element: array int[] + chỉ số int.
        VarHandle element =
                MethodHandles.arrayElementVarHandle(int[].class);

        State state = new State();
        int[] numbers = {10, 20, 30};

        System.out.println("instance varType="
                + instance.varType().getSimpleName());
        System.out.println("instance coordinates="
                + instance.coordinateTypes().stream()
                          .map(Class::getSimpleName).toList());
        System.out.println("static varType="
                + global.varType().getSimpleName());
        System.out.println("static coordinates="
                + global.coordinateTypes().size());
        System.out.println("array varType="
                + element.varType().getSimpleName());
        System.out.println("array coordinates="
                + element.coordinateTypes().stream()
                         .map(Class::getSimpleName).toList());

        MethodType getType =
                instance.accessModeType(VarHandle.AccessMode.GET);
        MethodType setType =
                element.accessModeType(VarHandle.AccessMode.SET);
        System.out.println("instance GET type="
                + getType.parameterCount() + "/"
                + getType.returnType().getSimpleName());
        System.out.println("array SET type="
                + setType.parameterCount() + "/"
                + setType.returnType().getSimpleName());

        System.out.println("instance initial=" + (int) instance.get(state));
        instance.set(state, 4);
        System.out.println("instance after set=" + (int) instance.get(state));

        boolean changed = instance.compareAndSet(state, 4, 9);
        System.out.println("instance CAS="
                + changed + "/" + (int) instance.get(state));
        int before = (int) instance.getAndAdd(state, 3);
        System.out.println("instance add="
                + before + "/" + (int) instance.get(state));

        System.out.println("static initial=" + (long) global.get());
        global.set(200L);
        System.out.println("static after set=" + (long) global.get());

        System.out.println("array initial=" + (int) element.get(numbers, 1));
        element.set(numbers, 1, 25);
        System.out.println("array after set="
                + (int) element.get(numbers, 1));
        System.out.println("array CAS="
                + (boolean) element.compareAndSet(numbers, 1, 25, 27));
        System.out.println("array data=" + Arrays.toString(numbers));

        Field f = State.class.getDeclaredField("count");
        VarHandle reflected = lookup.unreflectVarHandle(f);
        System.out.println("unreflect count="
                + (int) reflected.get(state));

        VarHandle finalField =
                lookup.findVarHandle(State.class, "label", String.class);
        System.out.println("final read="
                + (String) finalField.get(state));
        System.out.println("final SET supported="
                + finalField.isAccessModeSupported(VarHandle.AccessMode.SET));
        try {
            finalField.set(state, "other");
            System.out.println("unexpected final write");
        } catch (UnsupportedOperationException ex) {
            System.out.println("final SET=UnsupportedOperationException");
        }

        try {
            int ignored = (int) instance.get();
            System.out.println("unexpected arity=" + ignored);
        } catch (WrongMethodTypeException ex) {
            System.out.println("missing receiver=WrongMethodTypeException");
        }

        try {
            int ignored = (int) element.get(numbers, 3);
            System.out.println("unexpected index=" + ignored);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("bad index=ArrayIndexOutOfBoundsException");
        }
    }
}
```

Biên dịch và chạy trong thư mục có file:

```bash
javac VarHandleCreationDemo.java
java VarHandleCreationDemo
```

**Stdout (đã đối chiếu bằng biên dịch và chạy thật trên JDK hỗ trợ Java 17+):**

```text
instance varType=int
instance coordinates=[State]
static varType=long
static coordinates=0
array varType=int
array coordinates=[int[], int]
instance GET type=1/int
array SET type=3/void
instance initial=1
instance after set=4
instance CAS=true/9
instance add=9/12
static initial=100
static after set=200
array initial=20
array after set=25
array CAS=true
array data=[10, 27, 30]
unreflect count=12
final read=fixed
final SET supported=false
final SET=UnsupportedOperationException
missing receiver=WrongMethodTypeException
bad index=ArrayIndexOutOfBoundsException
```

### 6.1. Giải thích từng nhóm output

**Nhóm 1 – metadata (dòng 1–8).** Instance field cần một receiver `State`. Static field có `0` coordinate. Array element cần `int[]` và `int` index. `GET` của instance trả `int` và có 1 tham số; `SET` của array trả `void` và nhận 3 tham số (mảng, index, giá trị).

**Nhóm 2 – instance (dòng 9–12).** `state.count` bắt đầu 1, `set(state,4)` đưa lên 4. `compareAndSet(state,4,9)` trả `true` và ghi 9 vì expected value khớp. `getAndAdd(state,3)` trả **giá trị cũ** 9 và sau đó biến thành 12. Tất cả thao tác dùng cùng VarHandle nhưng cung cấp receiver object.

**Nhóm 3 – static (dòng 13–14).** `global.get()` không có tham số; `global.set(200L)` ghi long field của class và không cần bất kỳ `State` nào.

**Nhóm 4 – array (dòng 15–18).** `element.get(numbers,1)` trả 20; `set(numbers,1,25)` ghi vào chỉ số 1, rồi CAS từ 25 thành 27. Các phần tử khác không thay đổi.

**Nhóm 5 – tạo từ `Field` và final (dòng 19–22).** `lookup.unreflectVarHandle(f)` truy cập đúng biến `count` đang bằng 12. Handle cho field `final label` **đọc được** nhưng mode `SET` báo `false` và khi thử ghi sẽ có `UnsupportedOperationException`. Đừng dùng quyền private hợp lệ để suy ra final có thể viết.

**Nhóm 6 – lỗi (dòng 23–24).** `instance.get()` thiếu receiver, sai chữ ký signature-polymorphic và dẫn tới `WrongMethodTypeException`. `element.get(numbers,3)` vượt chỉ số của mảng dài 3, dẫn tới `ArrayIndexOutOfBoundsException`.

### 6.2. Vì sao ví dụ dùng nested class?

`State` là nested class nằm trong cùng top-level class `VarHandleCreationDemo`. Java 11+ có khái niệm nestmates, cho phép các thành viên của một nest truy cập private members với quyền phù hợp. Vì thế `MethodHandles.lookup()` tại `VarHandleCreationDemo.main` tìm được private fields `State.count`, `State.total` và `State.label` một cách hợp lệ.

Nếu đưa `State` sang module khác, giữ nguyên đoạn `MethodHandles.lookup()` có thể **không còn đủ quyền**. Quyền của `Lookup` không gắn với tên method `findVarHandle` mà gắn với class nhận lookup và ranh giới module. Đừng suy diễn rằng ví dụ private field này sẽ hoạt động từ mọi package.

## 7. Các chế độ truy cập sau khi đã tạo handle

Khi mới học tạo VarHandle, cần phân biệt rõ **tạo handle thành công** và **mọi access mode đều sử dụng được**. `VarHandle.AccessMode` liệt kê các mode như `GET`, `SET`, `GET_VOLATILE`, `SET_VOLATILE`, `COMPARE_AND_SET`, `GET_AND_ADD` v.v.

| Nhóm | Ví dụ lệnh | Ý nghĩa ngắn |
| --- | --- | --- |
| Plain read/write | `get`, `set` | Đọc/ghi biến theo semantics plain |
| Opaque | `getOpaque`, `setOpaque` | Truy cập opaque theo Java Memory Model |
| Acquire/release | `getAcquire`, `setRelease` | Hỗ trợ pattern đồng bộ acquire/release |
| Volatile | `getVolatile`, `setVolatile` | Đọc/ghi với semantics volatile |
| Atomic compare-update | `compareAndSet`, `compareAndExchange` và biến thể | So sánh expected value, cập nhật có điều kiện |
| Atomic read-modify-write | `getAndSet`, `getAndAdd` và biến thể hỗ trợ | Đọc giá trị cũ và cập nhật nguyên tử |

Các mode cần được lựa chọn dựa trên **đặc tính đồng bộ giữa các luồng**. `getAndAdd` có ý nghĩa khác với hai lệnh `int old=(int)vh.get(...); vh.set(...,old+1)`: phép đọc rồi ghi riêng lẻ không tự thành một thao tác atomic read-modify-write.

Tuy nhiên, phạm vi bài này là **factory và tọa độ**; chỉ cần nắm rằng một handle được tạo ra có một tập **supported access modes** phụ thuộc loại biến và kiểu dữ liệu. Ví dụ `getAndAdd` không phải phép cộng có nghĩa với mọi kiểu tham chiếu, còn VarHandle cho field `final` không hỗ trợ ghi.

Trước khi dùng mode có thể không hỗ trợ, kiểm tra:

```java
// Trích đoạn: finalField đã được tạo trong ví dụ chính.
boolean canWrite =
        finalField.isAccessModeSupported(VarHandle.AccessMode.SET);
if (!canWrite) {
    System.out.println("Final field chỉ hỗ trợ các mode hợp lệ.");
}
```

Nếu cố gọi một mode không hỗ trợ, Java có thể ném `UnsupportedOperationException` **ngay trong lời gọi mode**, như ví dụ đã chạy. Ngay cả một mode được hỗ trợ vẫn có thể gặp lỗi do sai tọa độ, sai kiểu, null hoặc index out of bounds.

### 7.1. Dạng chữ ký tiêu biểu ngoài `get`/`set`

Đối với `int count` (instance):

```text
countHandle.compareAndSet(state, expectedInt, newInt) -> boolean
countHandle.getAndAdd(state, deltaInt)                 -> int cũ
```

Đối với `long total` (static):

```text
totalHandle.compareAndSet(expectedLong, newLong) -> boolean
totalHandle.getAndAdd(deltaLong)                 -> long cũ
```

Đối với `int[]` element:

```text
arrayHandle.compareAndSet(array, index, expectedInt, newInt) -> boolean
arrayHandle.getAndAdd(array, index, deltaInt)                -> int cũ
```

Mẫu chung: **tọa độ trước, đối số của thao tác sau**. Sai thứ tự có thể dẫn đến `WrongMethodTypeException` hoặc lỗi chuyển kiểu. Những dạng trên minh họa mode thường hỗ trợ cho `int`/`long` writable; không tự động áp dụng cho `String` hoặc final field.

## 8. Các con đường tạo handle khác và kiểm soát quyền truy cập

### 8.1. `Lookup.unreflectVarHandle(Field)`

Khi một framework đã có `java.lang.reflect.Field` từ khâu scan metadata, có thể chuyển nó thành VarHandle:

```java
Field field = State.class.getDeclaredField("count");
VarHandle vh = MethodHandles.lookup().unreflectVarHandle(field);
```

Trong ví dụ hoàn chỉnh, `Field` này là private nhưng lookup của cùng nest có quyền; `vh.get(state)` thành công. `unreflectVarHandle` tự nhận ra field đó là instance/static và xác định coordinate types tương ứng.

Đừng hiểu `unreflectVarHandle` là bỏ qua mọi access check. Access tới private field vẫn dựa trên các quyền thích hợp theo `Lookup` và cơ chế Reflection/module. `Field.getDeclaredField` có thể **tìm được metadata** nhưng chưa có nghĩa nơi gọi được phép thực hiện deep access.

### 8.2. `privateLookupIn` khi cần private access hợp lệ

Với một class khác mà module/package policy cho phép private access, có thể tạo lookup có quyền tương ứng bằng `MethodHandles.privateLookupIn`:

```java
// Trích đoạn: OtherType là class do ứng dụng sở hữu hoặc có quyền hợp lệ.
MethodHandles.Lookup privateLookup =
        MethodHandles.privateLookupIn(
                OtherType.class, MethodHandles.lookup());

VarHandle secret = privateLookup.findVarHandle(
        OtherType.class, "secret", int.class);
```

Đây chỉ là **trích đoạn minh họa**, không phải ví dụ độc lập: cần khai báo `OtherType` có instance field `int secret` và đặt code trong môi trường có quyền. `privateLookupIn` **không tự vượt ranh giới module**; nếu package nguồn chưa được mở cho module gọi hoặc caller lookup thiếu quyền, lời gọi vẫn thất bại. Trường hợp thực nghiệm Java 17+ có thể dùng `opens` trong `module-info.java` hoặc `--add-opens=source.module/package=target.module` ở JVM đúng tiến trình, nếu chính sách dự án cho phép. Cờ `--add-opens` chỉ là cấu hình bổ sung quyền; tốt nhất vẫn ưu tiên API công khai.

### 8.3. Khác biệt giữa `findVarHandle`, `unreflectVarHandle` và `arrayElementVarHandle`

- `findVarHandle`/`findStaticVarHandle` tìm field theo **class + tên + field type**; phù hợp khi biết trước mô tả field.
- `unreflectVarHandle` bắt đầu từ một đối tượng `Field` sẵn có; phù hợp với framework quét metadata, nhưng không miễn quyền truy cập.
- `arrayElementVarHandle` nhận **array class** và không có field name hay lookup vì phần tử array không phải một field khai báo trong một class người dùng.
- Cả ba loại handle vẫn dùng cùng mô hình access modes và coordinate types. Không cần viết ba framework hoàn toàn khác nhau; phần logic khác nhau chủ yếu ở **factory** và **tọa độ**.

### 8.4. Tránh truy cập JDK private internals khi không cần thiết

Không nên lấy ví dụ sản phẩm bằng cách ghi private field của những class lõi `java.base`. Thực nghiệm với field trong class do mình sở hữu là cách an toàn, ổn định và dễ đối chiếu. Ngay cả khi thay đổi JVM flags để mở package, một private field của JDK vẫn là **implementation detail**, không phải contract công khai.

## 9. Lỗi thường gặp: triệu chứng, nguyên nhân và cách sửa

| Triệu chứng | Nguyên nhân có khả năng | Cách xử lý |
| --- | --- | --- |
| `NoSuchFieldException` khi `findVarHandle` | Sai tên field, sai loại field/type, hoặc class không có field tương ứng | Kiểm tra tên chính xác, `int.class` vs `Integer.class`, class được tra cứu; xác nhận field có thật |
| `IllegalAccessException` khi lookup | `Lookup` thiếu quyền private/package/protected hoặc module chặn | Xem scope của lookup, dùng public API hoặc `privateLookupIn` với quyền phù hợp |
| Có handle nhưng `get()` sai với instance field | Thiếu receiver coordinate `State` | Dùng `get(state)`; kiểm tra `coordinateTypes()` |
| Truyền receiver cho static field | Static coordinate list trống | Dùng `global.get()` và `global.set(value)` |
| `WrongMethodTypeException` | Signature-polymorphic call site không khớp về arity/kiểu/return | Kiểm tra `accessModeType(...)` và cast kiểu trả về chính xác, nhất là primitive |
| `ArrayIndexOutOfBoundsException` | Index array âm/quá giới hạn | Kiểm tra `0 <= index && index < array.length` |
| `NullPointerException` khi thao tác array/instance | Receiver hay array `null` | Kiểm tra input trước khi gọi |
| `UnsupportedOperationException` khi ghi field `final` | Mode SET không hỗ trợ | Kiểm tra `isAccessModeSupported(SET)` và xem field có writable không |
| `UnsupportedOperationException` với `getAndAdd` | Kiểu biến hoặc quyền khiến access mode không được hỗ trợ | Chọn access mode hỗ trợ, không ép phép cộng lên kiểu bất kỳ |
| `IllegalArgumentException` tại `arrayElementVarHandle` | Truyền non-array class, chẳng hạn `String.class` | Dùng `String[].class` hoặc kiểu array hợp lệ |
| Truy cập được trong class demo nhưng không dùng được giữa module | Lookup/module openness khác | Xác định nơi tạo `Lookup`, module khai báo field và chính sách `exports`/`opens` |

### 9.1. Vì sao `Field` tồn tại không đồng nghĩa VarHandle tạo được?

`Class.getDeclaredField(name)` là truy vấn metadata: tìm field **được khai báo** trong class, bất kể public/private. Nhưng tạo một VarHandle có khả năng thực thi quyền truy cập field yêu cầu một `Lookup` phù hợp. Nếu tool đọc được tên field nhưng không thể tạo handle, cần xem access control trước, không tự động gán lỗi cho tên field.

### 9.2. Không đoán kiểu theo boxing

Các lời gọi signature-polymorphic cần type theo mô hình JVM:

```java
// int field:
int n = (int) countHandle.get(state);

// long static field:
long sum = (long) totalHandle.get();
```

Trên đây là **trích đoạn**, cần các handle đã tạo. Đừng dùng `Integer.class` để tìm `int` field; cũng đừng cho rằng `(Object)handle.get(...)` là tương đương `(int)handle.get(...)` trong mọi trường hợp. `VarHandle` có thể cung cấp các cơ chế chuyển đổi thích hợp trong một số access modes, nhưng kiểu chính xác và access-mode type vẫn là nguồn sự thật để chẩn đoán.

### 9.3. Không dùng field name như "địa chỉ" phần tử mảng

Phần tử `array[index]` không xuất hiện như một field tên `"0"` hay `"length[1]"` trên class; tạo handle array element bằng `MethodHandles.arrayElementVarHandle`. `array.length` là thông tin kích thước array, không phải một writable element VarHandle. Một array VarHandle có thể dùng với bất kỳ mảng tương thích khi cung cấp đúng tọa độ runtime.

### 9.4. Không nhầm VarHandle với MethodHandle

`VarHandle` biểu diễn biến và các truy cập theo **access mode**. `MethodHandle` biểu diễn phép gọi. Có thể tạo MethodHandle từ một VarHandle bằng `toMethodHandle(VarHandle.AccessMode.GET)` nếu thật sự cần tích hợp với pipeline method handles, nhưng đó là **bước chuyển đổi thêm**, không bắt buộc cho bài toán tạo VarHandle.

Ví dụ:

```java
// Trích đoạn, giả định import java.lang.invoke.*.
MethodHandle getter =
        instance.toMethodHandle(VarHandle.AccessMode.GET);
int n = (int) getter.invokeExact(state);
```

Ở đây `getter` có type tương đương `(State)int`; `invokeExact` áp dụng quy tắc chính xác của MethodHandle, khác với `instance.get(state)` là access-mode invocation của VarHandle. Không nên chọn `toMethodHandle` chỉ để đọc field đơn giản, khi `get` đã đủ.

## 10. Quy trình chọn factory trong một ứng dụng thực tế

Giả sử framework đang nhận một field descriptor và muốn có một bộ truy cập nhanh, có thể áp dụng quy trình:

1. **Xác định biến cần thao tác**: là instance field, static field hay array element? Không suy luận chỉ từ tên field; xác minh khai báo `static`/kiểu array.
2. **Xác định đúng type**: lấy `field.getType()` khi có `Field`, hoặc dùng `int.class`, `long.class`, `String.class`... khớp chính xác.
3. **Chọn factory**:
   - instance → `findVarHandle(declaringClass,name,fieldType)`;
   - static → `findStaticVarHandle(declaringClass,name,fieldType)`;
   - array element → `arrayElementVarHandle(arrayClass)`;
   - có `Field` sẵn → cân nhắc `unreflectVarHandle(field)`.
4. **Cấp `Lookup` đúng quyền**. Ưu tiên tạo trong class/module sở hữu field. Với private field của class khác, kiểm tra module access rules và `privateLookupIn` trước khi dùng flags.
5. **Đọc metadata của handle**: `varType()` và `coordinateTypes()`; không tự đoán rằng biến static cần một receiver hoặc mảng 2D cần hai index trong cùng một VarHandle.
6. **Xác định access mode** cần dùng và kiểm tra `isAccessModeSupported(...)` khi không chắc chắn, đặc biệt với field `final` hoặc phép cộng nguyên tử.
7. **Dựng call site đúng chữ ký**; kiểm tra `accessModeType(...)` khi gặp lỗi. Tách tọa độ ra khỏi expected/new value/delta để bảo đảm đúng thứ tự.
8. **Test các trường hợp biên**: receiver null, array null, index âm/quá dài, sai kiểu, field không tồn tại, field final và thiếu quyền.
9. **Cache handle hợp lệ khi cần**, nhưng không giả định cùng một `Lookup` sẽ có quyền ở mọi module/điểm chạy.
10. **Đánh giá nhu cầu đồng bộ**: chỉ khi mục tiêu là thao tác đa luồng mới chọn mode memory-ordering hoặc atomic phù hợp; tạo handle tự nó không làm những cập nhật plain trở thành atomic.

Một nguyên tắc về thiết kế API: lưu **metadata của loại biến** cùng handle. Ví dụ, một bộ phận wrapper biết trước `coordinateTypes().size()==0` cho static thì không nên yêu cầu caller truyền object vô ích. Với array thì khai báo rõ tọa độ `(array,index)` trong hợp đồng API. Tránh tạo những wrapper không phân biệt loại biến rồi trả lỗi lúc runtime do thiếu/thừa tọa độ.

## 11. Bài tập và câu hỏi kiểm tra

**Câu 1.** Có class `Account` chứa `private int balance;`. Nên dùng factory nào và truyền gì vào `get`?  
**Đáp án:** Với lookup có quyền phù hợp, `lookup.findVarHandle(Account.class,"balance",int.class)`; đọc bằng `(int) vh.get(accountInstance)`. Handle có một coordinate là `Account`.

**Câu 2.** Có `static long sequence` trong `Account`. Vì sao `vh.get(new Account())` sai?  
**Đáp án:** Handle static được tạo qua `findStaticVarHandle` có `coordinateTypes()=[]`. Dùng `(long)vh.get()`; không có receiver.

**Câu 3.** Tạo `MethodHandles.arrayElementVarHandle(byte[].class)`. `varType()` và coordinates là gì?  
**Đáp án:** `varType()=byte.class`, coordinates là `[byte[].class,int.class]`.

**Câu 4.** Muốn xử lý phần tử ở index 3 của mảng dài 3. Có cần tạo VarHandle mới không?  
**Đáp án:** Không. Index hợp lệ của mảng dài 3 là 0, 1, 2; `get(array,3)` sẽ lỗi. Sửa index hoặc kích thước mảng, không tạo handle khác.

**Câu 5.** `Field.getDeclaredField("secret")` thành công; `lookup.unreflectVarHandle(field)` luôn thành công chứ?  
**Đáp án:** Không. Metadata và quyền access là hai chuyện khác nhau. Lookup phải có quyền phù hợp với field và module.

**Câu 6.** Một handle đọc `private final String name` được tạo thành công. `set` có dùng được vì private access đã hợp lệ không?  
**Đáp án:** Không. Final field không hỗ trợ access mode ghi như field mutable; kiểm tra `isAccessModeSupported(SET)`. Ví dụ mục 6 cho `false` và `UnsupportedOperationException`.

**Câu 7.** Từ `String[][] matrix` dùng `arrayElementVarHandle(String[][].class)`. Kiểu phần tử là `String` hay `String[]`?  
**Đáp án:** `String[]` vì một phần tử của mảng 2 chiều ở mức ngoài là một hàng `String[]`. Tọa độ của handle là `(String[][],int)`.

**Câu 8.** `getAndAdd(state,5)` trên instance field `int` trả giá trị trước hay sau cập nhật?  
**Đáp án:** Nó trả **giá trị cũ** và thực hiện thao tác cộng nguyên tử nếu mode hỗ trợ. Ví dụ có `9/12` khi cộng 3 vào 9.

**Câu 9.** Chỉ có `VarHandle vh` và không biết nó trỏ tới biến nào. Cách biết nên gọi `get()` hay `get(receiver)` hoặc `get(array,index)`?  
**Đáp án:** Đọc `vh.coordinateTypes()` và `vh.varType()`; có thể xem thêm `vh.accessModeType(GET)`. Không đoán từ tên handle.

**Câu 10.** Một class nằm trong module khác, private field chưa mở cho module gọi. Có thể chỉ dùng `MethodHandles.lookup().findVarHandle(...)` để bỏ qua JPMS không?  
**Đáp án:** Không. Cần quyền lookup/module hợp lệ; cân nhắc public API, `opens`, hoặc `privateLookupIn` trong phạm vi được cho phép. Việc có tên và kiểu field đúng không cấp quyền truy cập.

## 12. Tổng kết và tài liệu chính thức

Ghi nhớ ba công thức:

```text
instance:
  findVarHandle(Owner.class, "field", FieldType.class)
  coordinateTypes = [Owner]
  get(owner), set(owner, value)

static:
  findStaticVarHandle(Owner.class, "field", FieldType.class)
  coordinateTypes = []
  get(), set(value)

array element:
  arrayElementVarHandle(ElementType[].class)
  coordinateTypes = [ElementType[], int]
  get(array, index), set(array, index, value)
```

Trong mã thực tế, `FieldType.class` ở trên là **ký hiệu mô tả** kiểu field, không phải literal Java hợp lệ khi `FieldType` là một primitive tùy ý. Ví dụ dùng `int.class`, `long.class` hoặc `String.class` tương ứng. Tương tự, `ElementType[].class` biểu diễn cú pháp kiểu mảng như `int[].class` và `String[].class`.

**Ba quyết định quan trọng nhất:**

- **Chọn đúng factory** để mô tả chính xác instance/static/array.
- **Chọn đúng tọa độ** trước khi gọi access mode, sau đó mới đưa giá trị/expected/delta.
- **Tách quyền Lookup và supported access modes** khỏi ý tưởng “đã tạo handle là được gọi mọi thao tác”. Final, modules, access modifiers và loại biến vẫn có hiệu lực.

Tài liệu chuẩn:

- [Oracle Java SE 17 — `VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): `varType()`, `coordinateTypes()`, `accessModeType()`, `isAccessModeSupported()` và các access modes.
- [Oracle Java SE 17 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `findVarHandle()`, `findStaticVarHandle()`, `unreflectVarHandle()` và quyền lookup.
- [Oracle Java SE 17 — `MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `arrayElementVarHandle()` và `privateLookupIn()`.
- [Oracle Java SE 17 — `MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): kiểu tham số/trả về của access mode và của MethodHandle.
