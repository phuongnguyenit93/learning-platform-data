# Thực hành ma trận lời gọi static, virtual, constructor và field với kiểm tra kiểu lẫn kết quả

> **Chương:** MethodHandle  
> **Module:** JAVA_VERSION_JAVA18 — luyện kiểm chứng hợp đồng API và hành vi của `MethodHandle` trên JDK đang dùng. Java 18 đưa vào JEP 416 để tái triển khai Core Reflection dựa trên Method Handles; các API `java.lang.invoke` trong bài vẫn được hỗ trợ trên JDK hiện đại.  
> **Mục tiêu:** Tạo bảy loại handle bằng `MethodHandles.Lookup`, đọc `MethodType` thực tế, gọi bằng `invokeExact`, kiểm tra trạng thái/kết quả và nhận diện lỗi kiểu, thiếu member hoặc thiếu quyền truy cập.

## 1. MethodHandle là gì và vì sao cần kiểm tra kiểu?

`MethodHandle` là đối tượng có kiểu, đại diện cho một thao tác có thể gọi được: phương thức static, phương thức instance (virtual), constructor, đọc field hoặc ghi field. Mỗi handle có một `MethodType` gồm **các kiểu tham số theo đúng thứ tự** và **kiểu trả về**.

Khác với `java.lang.reflect.Method.invoke(Object, Object...)` vốn nhận danh sách đối số dưới dạng `Object[]` và có cơ chế boxing/dispatch riêng, `MethodHandle.invokeExact(...)` yêu cầu **kiểu của lời gọi tại call site** khớp chính xác với `handle.type()` — bao gồm cả kiểu trả về mà mã nguồn đang yêu cầu.

Vì vậy khi thử một handle, phải kiểm tra **hai mặt**:

1. **Kiểu:** `handle.type()` đúng với chữ ký mong đợi.
2. **Hành vi:** kết quả trả về, trạng thái đối tượng hoặc field đã thay đổi đúng.

Chỉ thấy handle tạo thành công chưa đủ để chứng minh lời gọi ở call site đúng kiểu. Ngược lại, chỉ nhìn output mà không kiểm tra kiểu dễ che mất sự khác biệt giữa receiver, constructor và setter.

## 2. Hai loại chữ ký: kiểu dùng để tìm và kiểu handle trả về

Trong `MethodHandles.Lookup`, tham số `MethodType` đưa vào các hàm `findStatic`, `findVirtual` và `findConstructor` mô tả **thành viên cần tìm**. Kiểu `MethodHandle.type()` nhận được có thể khác vì API thêm receiver hoặc chuyển constructor thành factory.

Giả sử lớp `Account` khai báo:

~~~java
public static int triple(int value) { return value * 3; }
public int add(int delta) { points += delta; return points; }
public Account(String id, int points) { ... }
public int points;
public static int threshold;
~~~

Ma trận:

| Thao tác | Lookup | Kiểu dùng khi lookup | Kiểu của handle trả về |
| --- | --- | --- | --- |
| Static method | `findStatic(Account.class, "triple", …)` | `(int)int` | `(int)int` |
| Virtual method | `findVirtual(Account.class, "add", …)` | `(int)int` | `(Account,int)int` |
| Constructor | `findConstructor(Account.class, …)` | `(String,int)void` | `(String,int)Account` |
| Đọc instance field | `findGetter(Account.class, "points", int.class)` | Kiểu field: `int.class` | `(Account)int` |
| Ghi instance field | `findSetter(Account.class, "points", int.class)` | Kiểu field: `int.class` | `(Account,int)void` |
| Đọc static field | `findStaticGetter(Account.class, "threshold", int.class)` | Kiểu field: `int.class` | `()int` |
| Ghi static field | `findStaticSetter(Account.class, "threshold", int.class)` | Kiểu field: `int.class` | `(int)void` |

Ký hiệu `(A,B)R` có nghĩa handle nhận đối số kiểu `A` và `B`, trả về `R`. `()int` không có tham số. `void` là kiểu trả về, không phải một giá trị có thể ép kiểu sang `Object`.

**Ba quy tắc đáng nhớ:**

- `findVirtual`: khi tìm **không** đưa receiver vào `MethodType`; khi gọi handle **phải** truyền receiver ở vị trí đầu.
- `findConstructor`: khi tìm dùng return type `void.class`; khi gọi handle, kết quả là một instance của lớp cần khởi tạo.
- `findGetter`/`findSetter` và biến thể static: tham số thứ ba là **kiểu field** (`Class<?>`), không phải một `MethodType`.

## 3. Chuẩn bị lookup và các lớp ví dụ

Trước khi vào bài thực hành đầy đủ, cần hiểu `Lookup` quyết định quyền truy cập:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
~~~

`lookup()` tạo một lookup object gắn với ngữ cảnh lớp gọi. Quyền truy cập được kiểm tra **lúc tạo MethodHandle**, không thực hiện lại mỗi lần gọi handle. Trong ví dụ, các member dùng để thực hành đều `public` và được khai báo trong lớp lồng nhau dễ truy cập; không cần `setAccessible(true)` hoặc mở module bằng cờ JVM.

Khi xử lý một thư viện/module khác, lookup có thể thất bại vì visibility hoặc ranh giới module. `publicLookup()` chỉ dùng các quyền public phù hợp; `privateLookupIn(...)` yêu cầu điều kiện truy cập/module tương ứng. Không dùng các thủ thuật truy cập nội bộ JDK để né access check.

## 4. Static method: không có receiver

Đích:

~~~java
public static int triple(int value) {
    return value * 3;
}
~~~

Tìm handle:

~~~java
MethodHandle triple = lookup.findStatic(
        Account.class,
        "triple",
        MethodType.methodType(int.class, int.class));
~~~

Kiểu:

~~~text
lookup MethodType: (int)int
handle.type():     (int)int
~~~

Lời gọi chính xác:

~~~java
int result = (int) triple.invokeExact(7);
// result == 21
~~~

Không truyền instance `Account` vào trước tham số `7`. Đối với static method, receiver không tồn tại trong danh sách tham số của handle.

## 5. Virtual method: receiver được thêm vào handle

Đích:

~~~java
public int add(int delta) {
    points += delta;
    return points;
}
~~~

Tìm handle:

~~~java
MethodHandle add = lookup.findVirtual(
        Account.class,
        "add",
        MethodType.methodType(int.class, int.class));
~~~

Kiểu thực tế:

~~~text
lookup MethodType: (int)int
handle.type():     (Account,int)int
~~~

Lời gọi chính xác:

~~~java
Account account = new Account("A", 10);
int result = (int) add.invokeExact(account, 5);
// result == 15; account.points == 15
~~~

Receiver `account` ở vị trí đầu là bắt buộc. Nếu handle trỏ đến một virtual method có thể bị override, việc gọi handle trên receiver của subclass sẽ phân phối đến implementation phù hợp với **kiểu runtime của receiver**, giống cơ chế virtual dispatch trong Java.

Ví dụ nếu `BonusAccount` override `add(int)` để nhân đôi `delta` trước khi gọi `super.add(delta * 2)`, thì:

~~~java
Account account = new BonusAccount("B", 10);
int result = (int) add.invokeExact(account, 3);
// result == 16: implementation của BonusAccount được gọi.
~~~

Kiểu tĩnh tại call site vẫn là `Account` vì handle yêu cầu `(Account,int)int`. Không viết `add.invokeExact((BonusAccount) account, 3)` nếu chưa chuyển kiểu handle: `invokeExact` thấy kiểu receiver `BonusAccount` tại call site, không khớp `Account` trong `handle.type()`.

## 6. Constructor: tìm với void, gọi trả về object

Đích:

~~~java
public Account(String id, int points) {
    this.id = id;
    this.points = points;
}
~~~

Tìm handle:

~~~java
MethodHandle create = lookup.findConstructor(
        Account.class,
        MethodType.methodType(void.class, String.class, int.class));
~~~

So sánh hai kiểu:

~~~text
lookup MethodType: (String,int)void
handle.type():     (String,int)Account
~~~

`void` trong tham số tìm kiếm mô tả constructor descriptor trên JVM; handle được trả về hoạt động như factory nên trả về đối tượng mới.

~~~java
Account account = (Account) create.invokeExact("A", 10);
// account.id() == "A"; account.points == 10
~~~

Không gọi `findConstructor` với `MethodType.methodType(Account.class, String.class, int.class)`: return type truyền cho factory lookup phải là `void.class`.

## 7. Field: đọc và ghi instance/static với kiểu đúng

### 7.1. Instance getter

~~~java
MethodHandle getPoints =
        lookup.findGetter(Account.class, "points", int.class);

// type: (Account)int
int points = (int) getPoints.invokeExact(account);
~~~

Receiver là tham số duy nhất, và giá trị trả về có kiểu của field.

### 7.2. Instance setter

~~~java
MethodHandle setPoints =
        lookup.findSetter(Account.class, "points", int.class);

// type: (Account,int)void
setPoints.invokeExact(account, 25);
~~~

Setter cần receiver và giá trị mới. `invokeExact` trong câu lệnh trên có **return type void**. Không viết `Object ignored = setPoints.invokeExact(account, 25)`: khi đó call site yêu cầu return type `Object`, khác với `void` của handle.

### 7.3. Static getter và static setter

~~~java
MethodHandle getThreshold =
        lookup.findStaticGetter(Account.class, "threshold", int.class);
MethodHandle setThreshold =
        lookup.findStaticSetter(Account.class, "threshold", int.class);

// Getter: ()int — không có receiver.
int before = (int) getThreshold.invokeExact();

// Setter: (int)void — không có receiver.
setThreshold.invokeExact(90);
int current = (int) getThreshold.invokeExact(); // 90

// Khôi phục trạng thái dùng chung sau bài thử.
setThreshold.invokeExact(before);
~~~

Với static field, không truyền receiver. Nếu field là `final`, `findSetter` hoặc `findStaticSetter` thông thường bị từ chối bằng `IllegalAccessException`: Java không cho ghi một final field bằng các factory này. Khi cần thao tác atomic/concurrent trên field mutable, nên xem thêm `VarHandle` thay vì mặc định dùng getter/setter handle.

## 8. Ví dụ hoàn chỉnh: ma trận kiểu và assertion

Lưu mã sau vào `HandleMatrixDemo.java`. Mọi member và tình huống đều dùng API có trên Java 18 và JDK hiện đại; không cần thư viện ngoài.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class HandleMatrixDemo {
    public static class Account {
        private final String id;
        public int points;
        public static int threshold = 40;

        public Account(String id, int points) {
            this.id = id;
            this.points = points;
        }

        public String id() {
            return id;
        }

        public static int triple(int value) {
            return value * 3;
        }

        public int add(int delta) {
            points += delta;
            return points;
        }

        public void fail() {
            throw new IllegalStateException("Lỗi từ method đích");
        }
    }

    public static final class BonusAccount extends Account {
        public BonusAccount(String id, int points) {
            super(id, points);
        }

        @Override
        public int add(int delta) {
            return super.add(delta * 2);
        }
    }

    private static void checkType(
            String label, MethodHandle handle, MethodType expected) {
        if (!handle.type().equals(expected)) {
            throw new AssertionError(label + ": expected "
                    + expected + ", got " + handle.type());
        }
        System.out.println(label + " type = " + handle.type());
    }

    private static void check(String label, int expected, int actual) {
        if (expected != actual) {
            throw new AssertionError(label + ": expected "
                    + expected + ", got " + actual);
        }
        System.out.println(label + " = " + actual);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        // 1. Static: (int)int.
        MethodHandle triple = lookup.findStatic(
                Account.class,
                "triple",
                MethodType.methodType(int.class, int.class));
        checkType("static", triple,
                MethodType.methodType(int.class, int.class));
        check("static result", 21, (int) triple.invokeExact(7));

        // 2. Constructor: tìm (String,int)void;
        //    handle thực tế có type (String,int)Account.
        MethodHandle create = lookup.findConstructor(
                Account.class,
                MethodType.methodType(
                        void.class, String.class, int.class));
        checkType("constructor", create,
                MethodType.methodType(
                        Account.class, String.class, int.class));
        Account account = (Account) create.invokeExact("A", 10);
        if (!account.id().equals("A")) {
            throw new AssertionError("Constructor không gán id đúng");
        }
        check("constructor state", 10, account.points);

        // 3. Virtual: tìm (int)int;
        //    handle thực tế có type (Account,int)int.
        MethodHandle add = lookup.findVirtual(
                Account.class, "add",
                MethodType.methodType(int.class, int.class));
        checkType("virtual", add,
                MethodType.methodType(
                        int.class, Account.class, int.class));
        check("virtual result", 15, (int) add.invokeExact(account, 5));

        // 4. Instance getter: (Account)int.
        MethodHandle getPoints = lookup.findGetter(
                Account.class, "points", int.class);
        checkType("instance getter", getPoints,
                MethodType.methodType(int.class, Account.class));
        check("instance getter result", 15,
                (int) getPoints.invokeExact(account));

        // 5. Instance setter: (Account,int)void.
        MethodHandle setPoints = lookup.findSetter(
                Account.class, "points", int.class);
        checkType("instance setter", setPoints,
                MethodType.methodType(
                        void.class, Account.class, int.class));
        setPoints.invokeExact(account, 25);
        check("instance setter state", 25,
                (int) getPoints.invokeExact(account));

        // 6-7. Static field getter ()int và setter (int)void.
        MethodHandle getThreshold = lookup.findStaticGetter(
                Account.class, "threshold", int.class);
        MethodHandle setThreshold = lookup.findStaticSetter(
                Account.class, "threshold", int.class);
        checkType("static getter", getThreshold,
                MethodType.methodType(int.class));
        checkType("static setter", setThreshold,
                MethodType.methodType(void.class, int.class));

        int oldThreshold = (int) getThreshold.invokeExact();
        try {
            setThreshold.invokeExact(90);
            check("static setter state", 90,
                    (int) getThreshold.invokeExact());
        } finally {
            setThreshold.invokeExact(oldThreshold);
        }

        // Virtual dispatch: receiver có runtime type BonusAccount,
        // nhưng kiểu tĩnh ở invokeExact vẫn là Account.
        Account bonus = new BonusAccount("B", 10);
        check("virtual override", 16,
                (int) add.invokeExact(bonus, 3));

        // invokeExact phải khớp cả return type.
        try {
            long wrongReturnType = (long) triple.invokeExact(7);
            throw new AssertionError(
                    "Expected WrongMethodTypeException, got "
                            + wrongReturnType);
        } catch (WrongMethodTypeException expected) {
            System.out.println("wrong return type: WrongMethodTypeException");
        }

        // invoke có thể điều chỉnh kiểu cho phép theo asType:
        // int trả về được widening thành long.
        long adapted = (long) triple.invoke(7);
        if (adapted != 21L) {
            throw new AssertionError("invoke adaptation không đúng");
        }
        System.out.println("invoke adapted result = " + adapted);

        // Tên/descriptor sai được phát hiện lúc lookup.
        try {
            lookup.findStatic(
                    Account.class, "triple",
                    MethodType.methodType(int.class, long.class));
            throw new AssertionError("Expected NoSuchMethodException");
        } catch (NoSuchMethodException expected) {
            System.out.println("wrong lookup method: NoSuchMethodException");
        }

        try {
            lookup.findGetter(Account.class, "missing", int.class);
            throw new AssertionError("Expected NoSuchFieldException");
        } catch (NoSuchFieldException expected) {
            System.out.println("missing field: NoSuchFieldException");
        }

        // final field có thể đọc nếu đủ quyền, nhưng không thể tạo
        // setter theo findSetter.
        try {
            lookup.findSetter(Account.class, "id", String.class);
            throw new AssertionError("Expected IllegalAccessException");
        } catch (IllegalAccessException expected) {
            System.out.println("final field setter: IllegalAccessException");
        }

        // Exception từ method đích được truyền thẳng; không bọc
        // bằng InvocationTargetException như Method.invoke().
        MethodHandle fail = lookup.findVirtual(
                Account.class, "fail",
                MethodType.methodType(void.class));
        checkType("fail", fail,
                MethodType.methodType(void.class, Account.class));
        try {
            fail.invokeExact(account);
            throw new AssertionError("Expected IllegalStateException");
        } catch (IllegalStateException expected) {
            System.out.println("target failure: IllegalStateException");
        }

        System.out.println("ALL CHECKS PASSED");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac HandleMatrixDemo.java
java HandleMatrixDemo
~~~

Một số dòng đầu/kết quả quan trọng:

~~~text
static type = (int)int
static result = 21
constructor type = (String,int)Account
constructor state = 10
virtual type = (Account,int)int
virtual result = 15
instance getter type = (Account)int
instance getter result = 15
instance setter type = (Account,int)void
instance setter state = 25
static getter type = ()int
static setter type = (int)void
static setter state = 90
virtual override = 16
wrong return type: WrongMethodTypeException
invoke adapted result = 21
wrong lookup method: NoSuchMethodException
missing field: NoSuchFieldException
final field setter: IllegalAccessException
fail type = (Account)void
target failure: IllegalStateException
ALL CHECKS PASSED
~~~

Thông tin type hiển thị bằng `MethodType.toString()` có thể rút gọn tên class, tùy cách trình bày; phép kiểm tra chuẩn trong code là `handle.type().equals(expected)`. Nếu bất kỳ phép đối chiếu nào sai, chương trình ném `AssertionError` thay vì chỉ in một kết quả trông có vẻ hợp lệ.

## 9. invokeExact, invoke và asType: khi nào dùng?

| API | Yêu cầu kiểu ở call site | Dùng khi |
| --- | --- | --- |
| `invokeExact(...)` | **Khớp chính xác** kiểu tham số và kiểu trả về với `handle.type()`. | Code biết trước chữ ký và muốn kiểm chứng/khai thác một call site rõ kiểu. |
| `invoke(...)` | Cho phép các conversion tương thích với `MethodHandle.asType`. | Call site cần chuyển đổi boxing, unboxing, primitive widening hoặc reference casts được hỗ trợ. |
| `asType(MethodType)` | Tạo handle đã điều chỉnh sang kiểu mới nếu conversion được phép. | Muốn chuẩn hóa type của một handle **một lần** trước khi gọi trong hot path. |

Ví dụ `invokeExact` sai **chỉ vì return type**:

~~~java
MethodHandle mh = lookup.findStatic(
        Account.class, "triple", MethodType.methodType(int.class, int.class));

// Chính xác:
int ok = (int) mh.invokeExact(7);

// Sai: call site yêu cầu trả về long, trong khi handle trả về int.
long wrong = (long) mh.invokeExact(7); // WrongMethodTypeException
~~~

Cùng trường hợp đó, `invoke` có thể thực hiện widening `int -> long`:

~~~java
long value = (long) mh.invoke(7); // 21L
~~~

Hoặc chuyển handle trước:

~~~java
MethodHandle toLong = mh.asType(
        MethodType.methodType(long.class, int.class));
long value = (long) toLong.invokeExact(7); // 21L
~~~

Không phải mọi chuyển đổi đều được phép. `invoke` không tự sửa lỗi sai số lượng tham số hoặc biến một method instance thành static; lỗi kiểu có thể vẫn dẫn đến `WrongMethodTypeException` hoặc lỗi cast của conversion.

## 10. Ma trận lỗi và cách phân loại

| Trường hợp | Giai đoạn | Lỗi thường gặp | Hướng xử lý |
| --- | --- | --- | --- |
| Tìm static method không tồn tại hoặc sai descriptor | Lookup | `NoSuchMethodException` | Kiểm tra tên, kiểu trả về và từng parameter trong `MethodType`. |
| Tìm constructor với tham số sai | Lookup | `NoSuchMethodException` | Dùng `MethodType` có return type `void` và đúng các tham số của constructor. |
| Tìm field sai tên hoặc sai kiểu | Lookup | `NoSuchFieldException` | `findGetter`/`findSetter` dùng chính xác tên và `Class<?>` của field. |
| Thành viên không truy cập được | Lookup | `IllegalAccessException` | Kiểm tra quyền Lookup, visibility, module exports/opens theo API thích hợp. |
| Tạo setter cho final field | Lookup | `IllegalAccessException` | Chỉ dùng setter với field mutable; không phá tính bất biến. |
| Sai số tham số của invokeExact | Call site | `WrongMethodTypeException` | So `handle.type()` với kiểu symbolic của lời gọi. |
| Sai return type, kể cả setter `void` | Call site | `WrongMethodTypeException` | Để setter là câu lệnh void; ép kiểu return của getter/method đúng kiểu. |
| Receiver null cho instance member | Invocation | `NullPointerException` | Truyền receiver hợp lệ. |
| Method đích tự ném exception | Target | Chính exception của method đích | Xem exception gốc; `MethodHandle` không bọc kiểu `InvocationTargetException`. |

Đối với `Method.invoke`, các lỗi của method đích thường được bọc trong `InvocationTargetException`. Đối với `MethodHandle`, throwable từ method đích được truyền trực tiếp, nên hai API có cách quan sát exception khác nhau.

## 11. Sử dụng bindTo cho receiver cố định

Khi ứng dụng luôn gọi cùng một instance, có thể ràng buộc receiver vào virtual handle:

~~~java
MethodHandle unbound = lookup.findVirtual(
        Account.class, "add",
        MethodType.methodType(int.class, int.class));
// unbound.type(): (Account,int)int

Account account = new Account("bound", 5);
MethodHandle bound = unbound.bindTo(account);
// bound.type(): (int)int

int result = (int) bound.invokeExact(3); // 8
~~~

`bindTo` loại receiver khỏi danh sách tham số của handle, không đổi implementation đích hoặc tự nhân bản object. Đây là lựa chọn khi receiver cố định có ý nghĩa trong workload; không nên áp dụng cho registry thay receiver từng request nếu chi phí tạo handle mới sẽ lớn hơn lợi ích.

## 12. Kinh nghiệm kiểm chứng trên JDK hiện đại

1. **Đọc kiểu ngay sau lookup:** dùng `System.out.println(handle.type())` hoặc so `MethodType.equals()`.
2. **Phân biệt chữ ký lookup với chữ ký handle:** đặc biệt với virtual và constructor.
3. **Không quên receiver:** static method và static field không cần; virtual/instance field bắt buộc có.
4. **Kiểm tra kết quả lẫn side effect:** setter trả `void` nên phải đọc field sau khi ghi để xác minh.
5. **Dùng kiểu tĩnh chính xác tại call site:** `invokeExact` không tự mở rộng kiểu tham số/return.
6. **Khôi phục trạng thái static dùng chung:** tránh tác động lên những ca kiểm thử khác.
7. **Chọn Lookup có quyền vừa đủ:** access check thực hiện khi tạo handle; tránh mở private API không cần thiết.
8. **Không dùng kết luận “nhanh hơn reflection” vô điều kiện:** cần benchmark theo các kiểu call site và số lượng target thực tế nếu quan tâm hiệu năng.
9. **Nếu thao tác field cần tính atomic:** xem `VarHandle`; getter/setter handle không tự biến thao tác `read-modify-write` thành atomic.
10. **Phân biệt JEP 416 với tính năng API:** JEP 416 đổi implementation Core Reflection trong Java 18, không làm thay đổi ý nghĩa các ví dụ lookup/invoke ở đây.

## 13. Bài tập thực hành

**Bài 1 — Ma trận kiểu.** Tự ghi kết quả `handle.type()` cho đủ bảy handle trước khi chạy `HandleMatrixDemo`. Đối chiếu cột lookup type và handle type, giải thích vì sao constructor và virtual có type khác nhau.

**Bài 2 — Ép kiểu trả về.** Thay một dòng `(int) triple.invokeExact(7)` thành `(long) triple.invokeExact(7)` để quan sát `WrongMethodTypeException`. Sau đó thử `invoke` và `asType` với return `long`.

**Bài 3 — Virtual override.** Thêm một subclass override `add(int)` theo quy tắc khác. Gọi qua cùng handle tìm trên `Account.class` nhưng receiver là subclass và xác minh method thực tế được dispatch theo runtime type.

**Bài 4 — Field.** Thêm instance field `String note` và static field `long requests` (không final). Dự đoán rồi kiểm tra các kiểu handle: `(Account)String`, `(Account,String)void`, `()long`, `(long)void`. Dùng giá trị literal `long` như `5L` ở call site setter.

**Bài 5 — Truy cập và lỗi.** Thử tìm một tên method không tồn tại, field sai kiểu và setter của final field. Phân loại `NoSuchMethodException`, `NoSuchFieldException`, `IllegalAccessException`. Đưa exception từ code method đích ra ngoài qua handle và so với `Method.invoke`.

## 14. Câu hỏi tự kiểm tra

1. `MethodHandle.type()` cho biết những thành phần nào?
2. Vì sao `findVirtual` không khai báo receiver trong `MethodType` tham số, nhưng handle lại thêm receiver?
3. `findStatic` có thêm receiver vào kiểu handle không?
4. Vì sao `findConstructor` nhận return type `void` nhưng handle trả về object?
5. `findGetter` khác `findStaticGetter` thế nào về số tham số?
6. `findSetter` và `findStaticSetter` trả về kiểu gì?
7. Có nên ép kiểu trả về `Object` cho setter khi dùng `invokeExact` không?
8. `WrongMethodTypeException` liên quan đến giai đoạn lookup hay giai đoạn invocation?
9. Tại sao receiver tĩnh `BonusAccount` có thể làm `invokeExact` lỗi nếu handle yêu cầu `Account`?
10. Vì sao method được override có thể được gọi qua handle tìm trên superclass?
11. Tại sao không thể tạo setter thông thường cho `final` field?
12. `MethodHandle.invoke` khác `invokeExact` ở khả năng chuyển đổi kiểu thế nào?
13. Exception từ method đích được truyền ra khỏi `MethodHandle` thế nào?
14. `bindTo` làm thay đổi `MethodType` ra sao?

## Tài liệu tham khảo chính thức

- [Oracle JDK 18 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `findStatic`, `findVirtual`, `findConstructor` và các factory getter/setter; quyền truy cập, kiểu handle.
- [Oracle JDK 18 — `MethodHandle`](https://docs.oracle.com/en/java/javase/18/docs/api/java.base/java/lang/invoke/MethodHandle.html): `type()`, `invokeExact`, `invoke`, `asType`, `bindTo` và các lỗi kiểu.
- [Oracle JDK 26 — `MethodHandle`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandle.html): xác nhận hợp đồng signature-polymorphic invocation vẫn được hỗ trợ trên JDK hiện đại.
- [Oracle JDK 26 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): kiểm tra quy tắc truy cập và các API lookup hiện hành.
- [OpenJDK JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): bối cảnh Java 18, phân biệt thay đổi triển khai Core Reflection với hợp đồng API MethodHandle.
