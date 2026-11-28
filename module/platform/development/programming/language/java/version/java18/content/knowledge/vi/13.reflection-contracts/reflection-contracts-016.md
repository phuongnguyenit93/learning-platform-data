# `Field.get()`, `Field.set()` và accessor primitive: receiver, giá trị và giới hạn chuyển đổi kiểu

## 1. Mục tiêu bài học

Trong chương **Hợp đồng reflection** của `JAVA_VERSION_JAVA18`, chúng ta kiểm chứng hành vi của `java.lang.reflect.Field` khi đọc và ghi trường dữ liệu. Java 18 đã thay đổi cách cài đặt core reflection bên trong JDK (JEP 416); các hợp đồng công khai về receiver, kiểu giá trị, kiểm tra quyền truy cập và chuyển đổi kiểu vẫn là điều cần hiểu trên những JDK hiện đại.

Sau bài học, bạn có thể:

- Gọi đúng chữ ký `Field.get(Object receiver)` và `Field.set(Object receiver, Object value)`, kể cả khi trường là `static`.
- Giải thích tại sao `get(...)` trả về wrapper khi trường có kiểu primitive; `set(...)` thực hiện unboxing và **chỉ** cho phép chuyển đổi widening phù hợp.
- Chọn `getInt`, `getLong`, `setInt`, `setByte` và các primitive accessor khác, dự đoán trường hợp gọi hợp lệ hoặc ném `IllegalArgumentException`.
- Phân biệt lỗi receiver, lỗi kiểu giá trị, lỗi quyền truy cập theo JPMS và hạn chế đối với trường `final`.
- Xây dựng phép kiểm tra có đầu ra cụ thể thay vì suy luận từ ép kiểu Java trong mã nguồn.

**Phạm vi:** Chỉ trình bày các hợp đồng API còn áp dụng trên JDK đang được hỗ trợ. Không sử dụng API nội bộ, mẹo vượt quyền truy cập hoặc cách sửa trường `final` phụ thuộc vào hành vi cũ.

## 2. `Field` là gì và lấy đối tượng `Field` như thế nào?

Một `Field` mô tả một trường thành viên của một lớp hoặc interface, bao gồm tên, kiểu, modifiers và lớp khai báo. `Field` **không** chứa giá trị riêng của mọi instance; giá trị được đọc từ receiver tương ứng khi gọi accessor.

Ví dụ:

```java
class Account {
    public int balance = 100;
    public static String unit = "VND";
}

Account account = new Account();
java.lang.reflect.Field balance =
        Account.class.getDeclaredField("balance");

System.out.println(balance.getName());        // balance
System.out.println(balance.getType());        // int
System.out.println(balance.get(account));     // Integer(100), in ra 100
```

Hai cách tìm trường thường gặp:

- `getDeclaredField("name")` tìm trường được **khai báo trực tiếp** trong lớp, bất kể `public`, `private` hay `protected`; nó không tự cấp quyền đọc/ghi.
- `getField("name")` tìm trường `public` (kể cả trường `public` kế thừa).

`getDeclaredField(...)` và `getField(...)` có thể ném `NoSuchFieldException`. Sau khi tìm được `Field`, kiểm tra quyền truy cập và kiểu receiver vẫn diễn ra khi dùng `get` hoặc `set`.

## 3. Receiver: đối tượng nào được đọc hoặc ghi?

Hai chữ ký thực tế là:

```java
Object Field.get(Object obj) throws IllegalArgumentException, IllegalAccessException;
void Field.set(Object obj, Object value)
        throws IllegalArgumentException, IllegalAccessException;
```

`obj` chính là **receiver**. Đối với trường instance, receiver phải là thể hiện của lớp khai báo trường (hoặc subtype thích hợp). Đối với trường `static`, `obj` được `Field.get` và `Field.set` bỏ qua; cách truyền rõ ràng nhất là `null`.

| Trường cần thao tác | Receiver | Kết quả |
| --- | --- | --- |
| `Account.balance` — instance `int` | `new Account()` | Hợp lệ nếu quyền truy cập cho phép. |
| `Account.balance` | `null` | `NullPointerException`. |
| `Account.balance` | `new Object()` | `IllegalArgumentException` vì không phải instance thích hợp. |
| `Account.unit` — `static String` | `null` | Hợp lệ nếu quyền truy cập cho phép. |
| `Account.unit` | Một đối tượng bất kỳ | Receiver bị bỏ qua bởi `Field.get`/`set`; vẫn có thể đọc/ghi trường `static` nếu quyền truy cập cho phép. |

Ví dụ:

```java
Field unit = Account.class.getDeclaredField("unit");
System.out.println(unit.get(null));       // VND
unit.set(null, "USD");                    // Ghi vào trường static
System.out.println(Account.unit);         // USD
```

**Không nhầm receiver với `value`:** receiver xác định **instance chứa trường**; value là giá trị sẽ ghi. Ví dụ `balance.set(account, 125)` ghi `125` vào `account.balance`, trong đó `125` được boxing thành `Integer` khi truyền vào đối số `Object`.

Một điểm khác cần lưu ý: lần đọc hoặc ghi một trường `static` bằng reflection có thể kích hoạt khởi tạo lớp khai báo, nếu lớp đó chưa được khởi tạo. Nếu quá trình khởi tạo thất bại, bạn có thể nhận `ExceptionInInitializerError`. Điều này độc lập với quy tắc chọn receiver.

## 4. Hợp đồng của `get(Object)`: boxing giá trị primitive

`get(receiver)` có kiểu trả về `Object`.

- Trường reference như `String`, `Integer` hoặc `Object`: trả về tham chiếu đang lưu, có thể là `null`.
- Trường primitive như `byte`, `int`, `boolean` hoặc `double`: giá trị được **boxing** thành wrapper tương ứng (`Byte`, `Integer`, `Boolean`, `Double`, ...).
- `get` không biến `Byte` thành `Integer` chỉ vì mã gọi đang mong một giá trị `int`.

Ví dụ:

```java
class Data {
    public byte small = 7;
    public Integer boxed = 42;
    public String label = null;
}

Data data = new Data();
Field small = Data.class.getDeclaredField("small");
Field boxed = Data.class.getDeclaredField("boxed");
Field label = Data.class.getDeclaredField("label");

Object a = small.get(data);               // Byte
Object b = boxed.get(data);               // Integer
Object c = label.get(data);               // null

System.out.println(a.getClass());         // class java.lang.Byte
System.out.println(b.getClass());         // class java.lang.Integer
System.out.println(c == null);            // true
```

Vì `small.get(data)` là `Byte`, câu lệnh `Integer x = (Integer) small.get(data);` sẽ ném `ClassCastException`; việc cast reference **khác** với phép widening primitive từ `byte` sang `int`. Nếu bạn biết trường là `byte` và muốn kết quả `int`, có thể dùng `small.getInt(data)`.

## 5. Primitive getter: đọc theo kiểu đích có thể widening

`Field` cung cấp tám primitive getter: `getBoolean`, `getByte`, `getShort`, `getChar`, `getInt`, `getLong`, `getFloat`, `getDouble`.

Các phương thức này đọc giá trị của một **trường primitive** và chuyển nó về kiểu trả về bằng phép đồng nhất kiểu (identity) hoặc **widening primitive conversion**. Không có narrowing; `boolean` không chuyển sang kiểu số.

Bảng sau ghi **kiểu trường nguồn có thể đọc được** qua từng getter:

| Getter | Kiểu trường primitive được chấp nhận |
| --- | --- |
| `getBoolean(obj)` | `boolean` |
| `getByte(obj)` | `byte` |
| `getShort(obj)` | `byte`, `short` |
| `getChar(obj)` | `char` |
| `getInt(obj)` | `byte`, `short`, `char`, `int` |
| `getLong(obj)` | `byte`, `short`, `char`, `int`, `long` |
| `getFloat(obj)` | `byte`, `short`, `char`, `int`, `long`, `float` |
| `getDouble(obj)` | `byte`, `short`, `char`, `int`, `long`, `float`, `double` |

Ví dụ, nếu field có kiểu `char` với giá trị `'A'`, `getInt(receiver)` trả về số `65`, còn `getShort(receiver)` ném `IllegalArgumentException`. Một field có kiểu `long` đọc bằng `getDouble` có thể mất độ chính xác, dù phép widening là hợp lệ theo hợp đồng Java.

```java
class Values {
    public byte small = 7;
    public char letter = 'A';
    public long large = 9_007_199_254_740_993L;
}

Values v = new Values();
Field small = Values.class.getDeclaredField("small");
Field letter = Values.class.getDeclaredField("letter");
Field large = Values.class.getDeclaredField("large");

System.out.println(small.getInt(v));      // 7
System.out.println(letter.getInt(v));     // 65
System.out.println(large.getLong(v));     // 9007199254740993
System.out.println(large.getDouble(v));   // Có thể làm tròn
```

Primitive getter **không tự unbox trường reference**. Ví dụ, đối với một trường khai báo kiểu `Integer`, hãy dùng `field.get(receiver)` để nhận `Integer`; đừng gọi `field.getInt(receiver)` rồi cho rằng JDK bắt buộc phải unbox wrapper.

## 6. `set(Object, Object)`: unboxing rồi widening về kiểu trường

Khi ghi, hướng chuyển đổi là **từ đối số value sang kiểu trường đích**.

Đối với trường reference, giá trị phải tương thích theo quan hệ gán reference (hoặc `null`). Với trường primitive, `Field.set(obj, value)` thực hiện unboxing wrapper của value rồi kiểm tra xem có thể chuyển sang kiểu đích bằng identity hoặc widening primitive conversion hay không.

Ví dụ:

```java
class Counter {
    public int count;
    public byte flag;
    public long total;
    public String tag;
}

Counter counter = new Counter();
Field count = Counter.class.getDeclaredField("count");
Field flag = Counter.class.getDeclaredField("flag");
Field total = Counter.class.getDeclaredField("total");
Field tag = Counter.class.getDeclaredField("tag");

count.set(counter, Byte.valueOf((byte) 12));  // byte -> int: hợp lệ
total.set(counter, Integer.valueOf(100));     // int -> long: hợp lệ
tag.set(counter, null);                      // reference có thể nhận null

// Những lệnh sau ném IllegalArgumentException:
// flag.set(counter, Integer.valueOf(1));    // int -> byte: narrowing
// count.set(counter, Long.valueOf(10L));     // long -> int: narrowing
// count.set(counter, null);                  // không unbox được null
// count.set(counter, "123");                 // String không là wrapper số
```

Một giá trị nguyên trông có vẻ vừa đủ, ví dụ số `1`, **không** làm cho narrowing hợp lệ. Các ngoại lệ cú pháp khi gán hằng số ở compile time (chẳng hạn `byte b = 1;`) không được áp dụng như quy tắc rút gọn cho `Field.set`. Reflection kiểm tra kiểu thực của giá trị tại runtime.

Đối với reference, `tag.set(counter, "ok")` hợp lệ vì `String` gán được cho `String`; `tag.set(counter, new Object())` ném `IllegalArgumentException`. Nếu kiểu trường là `Integer`, `set(receiver, Integer.valueOf(5))` là cách diễn đạt rõ ràng; điều này không biến `Integer` field thành primitive `int` field.

## 7. Primitive setter: các hướng widening hợp lệ

Tương ứng với getter, `Field` có tám primitive setter: `setBoolean`, `setByte`, `setShort`, `setChar`, `setInt`, `setLong`, `setFloat`, `setDouble`. Để xét **trường primitive đích**, bảng sau cho thấy setter nào có thể ghi vào các kiểu trường nào:

| Setter với giá trị nguồn | Kiểu trường primitive đích chấp nhận |
| --- | --- |
| `setBoolean(obj, boolean)` | `boolean` |
| `setByte(obj, byte)` | `byte`, `short`, `int`, `long`, `float`, `double` |
| `setShort(obj, short)` | `short`, `int`, `long`, `float`, `double` |
| `setChar(obj, char)` | `char`, `int`, `long`, `float`, `double` |
| `setInt(obj, int)` | `int`, `long`, `float`, `double` |
| `setLong(obj, long)` | `long`, `float`, `double` |
| `setFloat(obj, float)` | `float`, `double` |
| `setDouble(obj, double)` | `double` |

Những bảng getter và setter có **hướng đọc/ghi ngược nhau**:

- `byte` field đọc bằng `getInt` là hợp lệ: `byte → int`.
- `byte` field ghi bằng `setInt` là không hợp lệ: `int → byte`.
- `int` field ghi bằng `setByte` là hợp lệ: `byte → int`.
- `int` field đọc bằng `getByte` là không hợp lệ: `int → byte`.

`char` không widening sang `short`, và `short` không widening sang `char`, dù cả hai dùng 16 bit. `boolean` đứng độc lập với tất cả kiểu số.

> **Giới hạn độ chính xác:** Widening không có nghĩa luôn bảo toàn chính xác số học. Chuyển từ một số `long` đủ lớn sang `float` hoặc `double` có thể làm tròn; hãy dùng đúng kiểu khi dữ liệu yêu cầu độ chính xác nguyên vẹn.

## 8. Demo độc lập: kiểm chứng receiver và chuyển đổi kiểu

Lưu file `ReflectionFieldContracts.java` bằng UTF-8:

```java
import java.lang.reflect.Field;

public final class ReflectionFieldContracts {
    static final class Data {
        public byte small = 7;
        public char letter = 'A';
        public int count = 10;
        public long large = 9_007_199_254_740_993L;
        public boolean active = true;
        public Integer boxed = 99;
        public String label = "draft";
        public static long shared = 100L;
        public final int stable = 5;
    }

    @FunctionalInterface
    interface ReflectiveAction {
        void run() throws ReflectiveOperationException;
    }

    static void expectIllegalArgument(
            String title, ReflectiveAction action)
            throws ReflectiveOperationException {
        try {
            action.run();
            throw new AssertionError("Expected IllegalArgumentException: " + title);
        } catch (IllegalArgumentException expected) {
            System.out.println(title + " -> IllegalArgumentException");
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Data data = new Data();

        Field small = Data.class.getDeclaredField("small");
        Field letter = Data.class.getDeclaredField("letter");
        Field count = Data.class.getDeclaredField("count");
        Field large = Data.class.getDeclaredField("large");
        Field boxed = Data.class.getDeclaredField("boxed");
        Field label = Data.class.getDeclaredField("label");
        Field shared = Data.class.getDeclaredField("shared");
        Field stable = Data.class.getDeclaredField("stable");

        System.out.println("get(small) wrapper: "
                + small.get(data).getClass().getSimpleName()); // Byte
        System.out.println("getInt(small): " + small.getInt(data)); // 7
        System.out.println("getInt(letter): " + letter.getInt(data)); // 65

        count.set(data, Byte.valueOf((byte) 12)); // unbox, widen byte -> int
        System.out.println("count after set(Byte): " + count.getInt(data)); // 12
        count.setInt(data, 13);
        System.out.println("count after setInt: " + count.getInt(data)); // 13

        expectIllegalArgument("small.setInt",
                () -> small.setInt(data, 1)); // int -> byte
        expectIllegalArgument("count.set(Long)",
                () -> count.set(data, Long.valueOf(14L))); // long -> int
        expectIllegalArgument("count.set(null)",
                () -> count.set(data, null)); // primitive cannot be null
        expectIllegalArgument("letter.getShort",
                () -> letter.getShort(data)); // char -> short
        expectIllegalArgument("boxed.getInt",
                () -> boxed.getInt(data)); // reference Integer is not int
        expectIllegalArgument("wrong receiver",
                () -> count.get(new Object()));

        try {
            count.get(null);
            throw new AssertionError("Expected NullPointerException");
        } catch (NullPointerException expected) {
            System.out.println("instance receiver null -> NullPointerException");
        }

        shared.setInt(null, 101); // int -> long, receiver null for static
        System.out.println("shared: " + shared.getLong(null)); // 101

        label.set(data, null); // allowed for reference fields
        System.out.println("label is null: " + (label.get(data) == null));

        System.out.println("large.getLong: " + large.getLong(data));
        System.out.println("large.getDouble: " + large.getDouble(data));
        System.out.println("stable (read only): " + stable.getInt(data));
    }
}
```

Biên dịch và chạy bằng JDK mà bạn đang kiểm chứng:

```shell
java -version
javac -version
javac -encoding UTF-8 ReflectionFieldContracts.java
java ReflectionFieldContracts
```

Một số dòng đầu ra **kỳ vọng**:

```text
get(small) wrapper: Byte
getInt(small): 7
getInt(letter): 65
count after set(Byte): 12
count after setInt: 13
small.setInt -> IllegalArgumentException
count.set(Long) -> IllegalArgumentException
count.set(null) -> IllegalArgumentException
letter.getShort -> IllegalArgumentException
boxed.getInt -> IllegalArgumentException
wrong receiver -> IllegalArgumentException
instance receiver null -> NullPointerException
shared: 101
label is null: true
large.getLong: 9007199254740993
large.getDouble: 9.007199254740992E15
stable (read only): 5
```

Demo này cố ý đặt trường trong lớp lồng và gọi từ lớp bao ngoài để có quyền truy cập hợp lệ theo quan hệ lớp/nest. Kết quả `getDouble` là một ví dụ rounding hợp lệ khi widening từ `long`; cách biểu diễn có thể khác theo định dạng in số.

Nếu chương trình ném `AssertionError` trước một thông báo dự kiến, hãy kiểm tra lại JDK, phiên bản mã nguồn và giả định ở phép thử tương ứng thay vì đánh dấu cả bài là đã kiểm chứng.

## 9. Ngoại lệ: phân loại theo nguyên nhân

| Triệu chứng | Điều kiện phổ biến | Hướng kiểm tra |
| --- | --- | --- |
| `NullPointerException` | `get(null)` hoặc `set(null, ...)` trên trường instance. | Kiểm tra receiver có khác `null` không. |
| `IllegalArgumentException` | Receiver không tương thích với lớp khai báo; kiểu value sai; primitive accessor yêu cầu narrowing. | Xem `getDeclaringClass()`, `getType()`, kiểu runtime của value và bảng widening. |
| `IllegalAccessException` | Access check không cho phép đọc/ghi trường, hoặc thao tác ghi bị cấm với trường theo giới hạn API. | Kiểm tra visibility, module boundary và tính `final`. |
| `InaccessibleObjectException` | Cố yêu cầu `setAccessible(true)` nhưng strong encapsulation của module không cho phép. | Xem khai báo `opens`/quyền truy cập phù hợp, không cố bypass. |
| `ExceptionInInitializerError` | Khởi tạo lớp khai báo trường `static` thất bại khi reflection kích hoạt nó. | Kiểm tra logic khởi tạo tĩnh. |
| `NoSuchFieldException` | Không tìm được trường theo tên/quy tắc của `getField` hoặc `getDeclaredField`. | Kiểm tra tên, lớp khai báo và việc trường có kế thừa hay không. |

Phân biệt ba nhóm hay nhầm:

1. **Sai receiver:** `Field` đúng nhưng `obj` là `null` hoặc không thuộc loại đối tượng phù hợp.
2. **Sai kiểu dữ liệu:** receiver đúng nhưng Java không có identity/widening phù hợp giữa kiểu nguồn và kiểu đích.
3. **Không đủ quyền truy cập:** receiver và kiểu dữ liệu có thể đúng, nhưng quy tắc truy cập Java/JPMS không cho phép thao tác.

Không nên xử lý mọi lỗi bằng cách gọi `setAccessible(true)`: lời gọi đó không sửa lỗi receiver, không nới quy tắc widening và không làm mọi trường `final` trở nên có thể ghi.

## 10. Kiểm tra quyền truy cập trên named module

Với JPMS, việc nhìn thấy một lớp hoặc lấy được metadata `Field` không có nghĩa có quyền can thiệp vào mọi trường. API phân biệt quyền truy cập thông thường với khả năng thực hiện **deep reflection** vào thành viên không `public`.

- `exports package.name` công khai các kiểu `public` trong package theo quy tắc truy cập module.
- `opens package.name to other.module` cho phép deep reflection từ module được chỉ định; phạm vi nên được mở hẹp theo nhu cầu thiết kế.
- `trySetAccessible()` trả về `true` nếu có thể bật quyền truy cập phản chiếu cho đối tượng `Field`, hoặc `false` khi không thể (các lỗi khác do API quy định vẫn có thể xuất hiện).

Ví dụ mã ứng dụng dùng metadata có kiểm soát:

```java
Field field = SomeType.class.getDeclaredField("internalCount");
if (field.trySetAccessible()) {
    Object value = field.get(instance);  // Vẫn kiểm tra receiver và kiểu.
    System.out.println(value);
} else {
    System.out.println("Package/module does not permit deep reflection");
}
```

Đây là **mẫu minh họa**, trong đó `SomeType` và `instance` đại diện cho kiểu/đối tượng thực của ứng dụng. Khi package nằm trong một named module khác, người duy trì module cần chủ động cấu hình `opens` phù hợp; không nên xem việc thay đổi khả năng truy cập của `Field` như một mẹo tránh quy tắc module.

### Trường `final` trên JDK hiện đại

Nên coi trường `final` là **chỉ đọc qua reflection** trong mã ứng dụng thông thường. Quyền ghi bằng reflection đối với `final` có điều kiện và ngày càng bị giới hạn trên JDK hiện đại, nhất là với `static final`, trường `final` của record hoặc hidden class. Không dựa vào `setAccessible(true)` để sửa `final`: cấu hình JDK và ràng buộc bảo toàn bất biến có thể ngăn thao tác, và các bản JDK mới có thể đưa ra cảnh báo hoặc hạn chế thêm.

Nếu cần thay đổi trạng thái trong ứng dụng, hãy thiết kế API setter, tạo đối tượng mới hoặc sử dụng cơ chế khởi tạo/serialization được hỗ trợ thay vì ghi đè bất biến bằng reflection.

## 11. Cách tự xây dựng ma trận kiểm thử theo hợp đồng

Một bài kiểm thử reflection nên ghi rõ **kiểu field nguồn/đích**, **kiểu accessor**, **receiver** và **kết quả dự kiến**. Ví dụ:

| Trường | Thao tác | Dự kiến | Lý do |
| --- | --- | --- | --- |
| `byte small` | `getInt(obj)` | Thành công | Widening `byte → int`. |
| `byte small` | `setInt(obj, 3)` | `IllegalArgumentException` | Narrowing `int → byte`. |
| `int count` | `set(obj, Byte.valueOf((byte) 3))` | Thành công | Unboxing rồi widening `byte → int`. |
| `int count` | `set(obj, Long.valueOf(3L))` | `IllegalArgumentException` | Narrowing `long → int`. |
| `char letter` | `getInt(obj)` | Thành công | Widening `char → int`. |
| `char letter` | `getShort(obj)` | `IllegalArgumentException` | Không có widening `char → short`. |
| `boolean active` | `getInt(obj)` | `IllegalArgumentException` | `boolean` không chuyển thành số. |
| `Integer boxed` | `getInt(obj)` | `IllegalArgumentException` | Primitive getter yêu cầu trường primitive thích hợp. |
| `String label` | `set(obj, null)` | Thành công | Reference có thể nhận `null`. |
| `static long shared` | `getLong(null)` | Thành công | Static field không cần instance receiver. |
| `int count` | `get(null)` | `NullPointerException` | Instance field thiếu receiver. |

Có thể thêm test `getFloat`/`getDouble` cho `long` lớn để chứng minh chuyển đổi widening hợp lệ dù kết quả có thể được làm tròn. Khi kiểm chứng trên nhiều JDK, ghi lại `java -version` và chỉ so sánh hành vi được bảo đảm bởi hợp đồng API.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `Field.get(obj)` của trường `byte` có trả về `int` vì Java thường tự nâng kiểu số nhỏ trong biểu thức không?

**Trả lời:** Không. Nó trả về `Byte` vì kiểu trường là `byte`. Muốn đọc thành `int`, dùng `getInt(obj)` với widening hợp lệ.

**Câu 2.** Vì sao `field.set(obj, 1)` không nhất thiết ghi được vào trường `byte`, trong khi `byte value = 1;` biên dịch được?

**Trả lời:** Biểu thức `1` được boxing thành `Integer` khi truyền vào đối số `Object`. Reflection không dùng quy tắc narrowing đặc biệt dành cho hằng số nguyên ở compile time; `int → byte` không là widening. Có thể truyền `Byte.valueOf((byte) 1)` hoặc dùng `setByte`.

**Câu 3.** Vì sao `getLong(obj)` có thể hợp lệ trên trường `int` nhưng `setLong(obj, 123L)` không?

**Trả lời:** Getter chuyển từ kiểu của trường `int` sang kiểu trả về `long` (widening), còn setter cần chuyển từ đối số `long` sang trường đích `int` (narrowing).

**Câu 4.** Với trường instance, `receiver == null` và receiver sai lớp có cho cùng ngoại lệ không?

**Trả lời:** Không. Instance receiver `null` gây `NullPointerException`; receiver khác kiểu phù hợp gây `IllegalArgumentException`.

**Câu 5.** Chỉ cần `getDeclaredField(...)` thành công là đọc được trường `private` của một named module khác?

**Trả lời:** Không. Lấy metadata và quyền truy cập giá trị là hai chuyện khác nhau; visibility, `exports`/`opens` và quy tắc JPMS vẫn được áp dụng.

## Tài liệu tham khảo

- Java SE API — `java.lang.reflect.Field`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Field.html
- Java SE API — `java.lang.reflect.AccessibleObject`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- Java Language Specification — Widening Primitive Conversion: https://docs.oracle.com/javase/specs/jls/se25/html/jls-5.html#jls-5.1.2
- OpenJDK JEP 416 — *Reimplement Core Reflection with Method Handles*: https://openjdk.org/jeps/416

Các đường dẫn Java SE 25 là tài liệu tham khảo cho API hiện đại; khi kiểm thử, hãy đối chiếu với tài liệu ứng với **đúng phiên bản JDK đang chạy**.
