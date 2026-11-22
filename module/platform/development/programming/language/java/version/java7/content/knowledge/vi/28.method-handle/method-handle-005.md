# Tra cứu getter và setter của trường bằng MethodHandles.Lookup

## 1. Khái niệm: truy cập trực tiếp một field qua MethodHandle

Trong Java, **MethodHandle** là một đối tượng biểu diễn lời gọi có thể thực thi với chữ ký kiểu cụ thể. Khi cần đọc hoặc ghi một **trường (field)** đã biết bằng tên, lớp khai báo và kiểu dữ liệu, **MethodHandles.Lookup** có các phương thức tạo handle cho thao tác truy cập trường:

- **findGetter(...)** tạo handle **đọc trường instance**.
- **findSetter(...)** tạo handle **ghi trường instance**.
- **findStaticGetter(...)** tạo handle **đọc trường static**.
- **findStaticSetter(...)** tạo handle **ghi trường static**.

Các phương thức này tra cứu **field thực sự**, không tự tìm các phương thức JavaBeans mang tên **getName()**, **setName(...)** hoặc **isActive()**. Đây là điểm phân biệt quan trọng: một trường tên **name** khác một phương thức tên **getName**. Nếu muốn gọi phương thức accessor, sử dụng **findVirtual/findStatic** với **MethodType** phù hợp, hoặc gọi API Java thông thường.

Ví dụ một trường instance:

~~~java
class Counter {
    int count;
}
~~~

Từ một ngữ cảnh có quyền truy cập **Counter.count**:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle getter =
        lookup.findGetter(Counter.class, "count", int.class);
MethodHandle setter =
        lookup.findSetter(Counter.class, "count", int.class);
~~~

Hai đoạn trên là mã **minh họa**, không phải chương trình chạy độc lập; đoạn thứ hai cần import **java.lang.invoke.MethodHandle**, **MethodHandles**, được đặt trong phương thức có xử lý hoặc khai báo lỗi tra cứu. **getter** đọc **count** của một đối tượng Counter; **setter** thay đổi đúng trường đó. Chúng không gọi một phương thức getter/setter tùy ý trong lớp.

**Khi nào hữu ích?** Các thư viện serialization, dependency injection, mapper, framework xử lý metadata, adapter runtime và công cụ tương tác với những field đã được xác minh có thể cần tạo handle một lần rồi gọi nhiều lần. Nếu lớp và field được biết ngay tại nơi viết code và có quyền truy cập bình thường, cú pháp **object.field** hoặc public accessor thường rõ ràng và dễ bảo trì hơn.

## 2. Cú pháp tra cứu và chữ ký thực tế của handle

Bốn phương thức đều nhận **Class<?> refc**, **String name** và **Class<?> type**:

~~~java
MethodHandle findGetter(
        Class<?> refc, String name, Class<?> type)
        throws NoSuchFieldException, IllegalAccessException;

MethodHandle findSetter(
        Class<?> refc, String name, Class<?> type)
        throws NoSuchFieldException, IllegalAccessException;

MethodHandle findStaticGetter(
        Class<?> refc, String name, Class<?> type)
        throws NoSuchFieldException, IllegalAccessException;

MethodHandle findStaticSetter(
        Class<?> refc, String name, Class<?> type)
        throws NoSuchFieldException, IllegalAccessException;
~~~

Đây là **khai báo API rút gọn để học**, không phải mã đặt bên trong một chương trình. Ý nghĩa tham số:

- **refc**: lớp/interface mà việc phân giải field được thực hiện từ đó.
- **name**: tên **field**, phân biệt chữ hoa/chữ thường; không có tiền tố **get** hay **set**.
- **type**: **kiểu Java chính xác được khai báo của field**. Ví dụ **int.class** khác **long.class** và **Integer.class**; **String.class** khác **Object.class** dù Object là lớp cha.
- **Lookup**: đối tượng mang quyền truy cập của lớp gọi; việc tìm thấy field không có nghĩa tự động được quyền truy cập nó.

Với field có kiểu **T** nằm trên đối tượng **R**, bốn loại handle thường có **MethodType** như sau:

| Loại field | API tra cứu | Chữ ký của MethodHandle.type() | Cách gọi |
| --- | --- | --- | --- |
| **T field;** | findGetter(R.class, "field", T.class) | **(R)T** | Truyền receiver, nhận giá trị |
| **T field;** | findSetter(R.class, "field", T.class) | **(R,T)void** | Truyền receiver và giá trị mới |
| **static T field;** | findStaticGetter(R.class, "field", T.class) | **()T** | Không truyền receiver |
| **static T field;** | findStaticSetter(R.class, "field", T.class) | **(T)void** | Chỉ truyền giá trị mới |

**Receiver** là đối tượng chứa trường instance. Với trường static không có receiver trong chữ ký. Ví dụ một trường **int stock** của **Product**:

- Getter: **(Product)int**.
- Setter: **(Product,int)void**.
- Trường **static String stage**: getter **()String**, setter **(String)void**.

**Kiểu kết quả của setter luôn là void**. Không lấy giá trị trả về của setter như một kết quả mới. Kiểu kết quả của getter chính là kiểu field.

MethodHandle có chữ ký cụ thể, kiểm tra bằng **handle.type()**. Bản mô tả này khác **MethodType** dùng để tra cứu phương thức:

~~~java
// Field: truyền thẳng Class<?> của field.
lookup.findGetter(Product.class, "stock", int.class);

// Method: truyền MethodType của phương thức có tham số/kết quả.
lookup.findVirtual(
        Product.class,
        "getStock",
        java.lang.invoke.MethodType.methodType(int.class));
~~~

Đoạn thứ hai chỉ hợp lệ khi **Product thực sự khai báo hoặc kế thừa phương thức getStock() trả int**, có thể truy cập. Truy cập field và gọi phương thức có thể khác nhau về logic: getter method có thể validate, tính toán, cache hoặc có side effect, trong khi getter field đơn thuần thực hiện thao tác đọc trường tương ứng.

## 3. findGetter và findSetter đối với trường instance

Giả sử:

~~~java
class Account {
    int points;
}
~~~

Với một Lookup có quyền truy cập vào **Account.points**:

~~~java
MethodHandle readPoints =
        lookup.findGetter(Account.class, "points", int.class);
MethodHandle writePoints =
        lookup.findSetter(Account.class, "points", int.class);

// readPoints.type(): (Account)int
// writePoints.type(): (Account,int)void
~~~

Đây là ví dụ minh họa, cần biến **lookup**, import thích hợp và ngữ cảnh có thể ném exception. Một lời gọi chính xác sẽ có dạng:

~~~java
Account account = new Account();
writePoints.invokeExact(account, 25);
int points = (int) readPoints.invokeExact(account);
~~~

Mã phải được đặt trong phương thức có **throws Throwable** hoặc xử lý ngoại lệ của MethodHandle. **invokeExact** yêu cầu chữ ký call site đúng hoàn toàn: argument đầu tiên là **Account**, argument thứ hai là primitive **int** khi ghi, getter trả **int**.

Nếu field **int points** nhưng yêu cầu **long.class**:

~~~java
lookup.findGetter(Account.class, "points", long.class);
~~~

Lookup không thực hiện cast từ int sang long để chọn field. Yêu cầu field **points** có loại **long**, không khớp với khai báo **int**, nên tra cứu thất bại bằng **NoSuchFieldException**. Nếu cần chuyển kết quả từ int sang long khi gọi, hãy lấy handle đúng kiểu int trước rồi cân nhắc **asType(...)** hoặc chuyển đổi kết quả theo quy tắc Java.

### Đọc và ghi field không đồng nghĩa bảo đảm nghiệp vụ

Một getter/setter field handle không nhất thiết thực thi logic của các public accessor. Ví dụ **setPoints(int)** có thể cấm giá trị âm trong khi setter field cho **points** sẽ ghi trực tiếp, nếu Lookup có quyền. Do đó:

- Không dùng field setter để bỏ qua validation hoặc invariant của domain object.
- Không coi field setter là cơ chế thông báo thay đổi của framework, trừ khi framework được thiết kế và kiểm chứng để thực hiện việc đó.
- Kiểm tra kiểu và quyền truy cập ở **lookup time**, nhưng vẫn phải xác minh **giá trị/ngữ nghĩa nghiệp vụ** trước khi ghi.

## 4. findStaticGetter và findStaticSetter đối với trường static

Trường static thuộc lớp, nên handle không nhận instance. Ví dụ:

~~~java
class RuntimeConfig {
    static String mode = "dev";
}
~~~

Với Lookup có quyền truy cập:

~~~java
MethodHandle getMode =
        lookup.findStaticGetter(
                RuntimeConfig.class, "mode", String.class);
MethodHandle setMode =
        lookup.findStaticSetter(
                RuntimeConfig.class, "mode", String.class);

// getMode.type(): ()String
// setMode.type(): (String)void

setMode.invokeExact("prod");
String mode = (String) getMode.invokeExact();
~~~

Đây là ví dụ minh họa, không phải chương trình độc lập. Chữ ký **()String** nghĩa là không có tham số và trả String; **(String)void** nghĩa là nhận một String, không trả giá trị.

**Không được dùng findGetter/findSetter của instance để truy cập field static**. Sử dụng sai loại lookup có thể gây **IllegalAccessException**. Khi gọi một static field handle, lớp chứa field được khởi tạo theo quy tắc JVM nếu chưa khởi tạo.

**Cảnh báo thiết kế:** Một static mutable field là trạng thái dùng chung. Việc có handle để ghi không khiến thao tác trở nên an toàn trong môi trường đa luồng, không tự thêm đồng bộ và không bảo đảm tính nguyên tử của các phép cập nhật phức hợp.

## 5. Quyền truy cập: Lookup là một capability, không phải cách bỏ qua private

**MethodHandles.lookup()** trả Lookup có quyền phù hợp với **lớp gọi tại vị trí tạo Lookup**. Khi tra cứu, JVM kiểm tra liệu Lookup đó có được quyền thực hiện thao tác field tương đương hay không. Kiểm tra quyền thông thường diễn ra **khi tạo handle**, không lặp lại toàn bộ ở mỗi lần gọi.

Các trường hợp thường gặp:

- **public field trên lớp public có thể truy cập**: có thể dùng Lookup phù hợp hoặc **MethodHandles.publicLookup()**.
- **private field**: Lookup từ code không có quyền truy cập sẽ thất bại bằng **IllegalAccessException**.
- **package-private/protected**: chịu quy tắc truy cập Java và ngữ cảnh Lookup, không phải chỉ cần biết tên field là đủ.
- **module boundary**: trong ứng dụng Java dùng JPMS, quyền truy cập private qua **privateLookupIn** chịu yêu cầu về module, package **opens** và quyền của Lookup ban đầu.
- **final field**: getter được phép khi Lookup có quyền đọc; **findSetter** hoặc **findStaticSetter** cho trường **final** không tạo được setter bình thường, ngay cả khi trường đọc được.

### Sử dụng privateLookupIn có kiểm soát

Từ Java 9 trở đi, có thể dùng:

~~~java
MethodHandles.Lookup base = MethodHandles.lookup();
MethodHandles.Lookup memberLookup =
        MethodHandles.privateLookupIn(Target.class, base);

MethodHandle fieldGetter =
        memberLookup.findGetter(Target.class, "secret", String.class);
~~~

Đây là đoạn minh họa chỉ chạy khi **base thực sự có quyền tạo Lookup cho Target**. Nó không phải một lối thoát mọi hạn chế truy cập: khi Target thuộc module khác, package của Target cần được **open** phù hợp và base phải đáp ứng các điều kiện quyền của API. Nếu thiếu quyền, **privateLookupIn** ném **IllegalAccessException**. Không nên cố sửa quyền bằng cách mở bừa các package nội bộ hoặc dùng deep reflection trái hợp đồng module.

**Không phát tán Lookup có quyền cao hoặc các handle truy cập private tới code không tin cậy.** Một handle đã được tạo có thể mang quyền đọc/ghi vượt quá giao diện public dự kiến của object. Framework nên giới hạn nơi tạo, lưu và chia sẻ handle.

### final là ranh giới cần tôn trọng

~~~java
class ImmutableId {
    final long id = 123L;
}
~~~

Với Lookup có quyền đọc:

~~~java
MethodHandle idGetter =
        lookup.findGetter(ImmutableId.class, "id", long.class);
// Getter là hợp lệ nếu có quyền truy cập.

lookup.findSetter(ImmutableId.class, "id", long.class);
// IllegalAccessException: không thể tạo direct setter thông thường cho final.
~~~

Đây là minh họa; dòng findSetter cố ý biểu diễn lỗi và không nên đặt trong một luồng chạy bình thường mà không xử lý ngoại lệ. Tương tự, **static final** có thể đọc bằng static getter nhưng không có static setter hợp lệ. Không dùng các kỹ thuật sửa final bằng reflection sâu như một lựa chọn thường quy: có những ràng buộc đặc biệt và các JDK hiện đại ngày càng siết quyền ghi final. Với record, các component field cũng là final; hãy tạo instance mới khi cần thay đổi dữ liệu.

## 6. Ví dụ Java 17+: tra cứu, đọc, ghi, kiểm tra lỗi và quyền truy cập

Chương trình độc lập dưới đây chỉ dùng thư viện chuẩn của JDK, có trường **instance**, **static**, **private**, **final** và minh họa sự khác biệt giữa **lỗi lúc tìm handle** và **lỗi lúc gọi handle**. **Item** là lớp lồng trong cùng lớp chính; việc dùng **privateLookupIn** trong ví dụ hợp lệ nhờ ngữ cảnh quyền truy cập giữa các lớp cùng nest.

Lưu vào tệp **FieldLookupDemo.java**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.WrongMethodTypeException;

public class FieldLookupDemo {
    private static final class Item {
        private final long id;
        private String title;
        private int stock;
        private static String stage = "dev";

        Item(long id, String title, int stock) {
            this.id = id;
            this.title = title;
            this.stock = stock;
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup =
                MethodHandles.privateLookupIn(
                        Item.class, MethodHandles.lookup());

        MethodHandle titleGet =
                lookup.findGetter(Item.class, "title", String.class);
        MethodHandle titleSet =
                lookup.findSetter(Item.class, "title", String.class);
        MethodHandle stockGet =
                lookup.findGetter(Item.class, "stock", int.class);
        MethodHandle stockSet =
                lookup.findSetter(Item.class, "stock", int.class);
        MethodHandle stageGet =
                lookup.findStaticGetter(Item.class, "stage", String.class);
        MethodHandle stageSet =
                lookup.findStaticSetter(Item.class, "stage", String.class);
        MethodHandle idGet =
                lookup.findGetter(Item.class, "id", long.class);

        Item item = new Item(7L, "Pen", 3);

        System.out.println("getterType=" + titleGet.type());
        System.out.println("setterType=" + titleSet.type());
        System.out.println("staticGetterType=" + stageGet.type());
        System.out.println("staticSetterType=" + stageSet.type());

        System.out.println("before=" + (String) titleGet.invokeExact(item));
        titleSet.invokeExact(item, "Notebook");
        stockSet.invokeExact(item, 9);
        stageSet.invokeExact("prod");

        System.out.println("after=" + (String) titleGet.invokeExact(item));
        System.out.println("stock=" + (int) stockGet.invokeExact(item));
        System.out.println("id=" + (long) idGet.invokeExact(item));
        System.out.println("stage=" + (String) stageGet.invokeExact());

        try {
            lookup.findSetter(Item.class, "id", long.class);
        } catch (IllegalAccessException expected) {
            System.out.println("finalSetter=denied");
        }

        try {
            MethodHandles.publicLookup().findGetter(
                    Item.class, "title", String.class);
        } catch (IllegalAccessException expected) {
            System.out.println("publicLookup=denied");
        }

        try {
            lookup.findGetter(Item.class, "stock", long.class);
        } catch (NoSuchFieldException expected) {
            System.out.println("wrongFieldType=NoSuchFieldException");
        }

        try {
            long wrong = (long) stockGet.invokeExact(item);
            System.out.println(wrong);
        } catch (WrongMethodTypeException expected) {
            System.out.println("wrongCallSite=WrongMethodTypeException");
        }
    }
}
~~~

Biên dịch và chạy với **JDK 17+**:

~~~bash
javac FieldLookupDemo.java
java FieldLookupDemo
~~~

Kết quả:

~~~text
getterType=(Item)String
setterType=(Item,String)void
staticGetterType=()String
staticSetterType=(String)void
before=Pen
after=Notebook
stock=9
id=7
stage=prod
finalSetter=denied
publicLookup=denied
wrongFieldType=NoSuchFieldException
wrongCallSite=WrongMethodTypeException
~~~

Chương trình đã được kiểm tra bằng **JShell trên JDK 24** với đúng nội dung lớp và nhận các dòng kết quả trên. Nó sử dụng API cũng được hỗ trợ trong JDK 17. Lệnh **javac** và **java** ở trên là cách chạy dưới dạng tệp Java chuẩn.

**Giải thích:**

1. **titleGet.type()** là **(Item)String**: phải truyền Item; trả String. **titleSet.type()** là **(Item,String)void**: truyền Item và String, không trả kết quả.
2. Các handle của trường **static stage** không cần Item. **stageSet.invokeExact("prod")** ghi stage; **stageGet.invokeExact()** đọc.
3. **privateLookupIn** được tạo trong phạm vi được quyền truy cập vào lớp lồng Item; vì vậy đọc/ghi **private title, stock, stage** thành công.
4. **final long id** chỉ được đọc trong chương trình. Việc tạo setter trực tiếp cho field final thất bại và bị bắt bằng **IllegalAccessException**.
5. **publicLookup()** không có quyền tìm private field của private nested class, nên bị từ chối.
6. **stock** thực sự có kiểu int; yêu cầu tra cứu field với **long.class** không khớp, dẫn tới **NoSuchFieldException**.
7. **stockGet** trả int. Dòng **long wrong = (long) stockGet.invokeExact(item)** yêu cầu call-site trả **long**, không khớp với getter **(Item)int**, vì thế ném **WrongMethodTypeException**.

**Chú ý:** Dòng **main throws Throwable** thuận tiện cho bài chạy độc lập bởi **invokeExact** có thể chuyển ngoại lệ từ mục tiêu; code production nên xác định chính sách xử lý lỗi, quyền truy cập và cập nhật dữ liệu riêng.

## 7. Tra cứu thành công chưa đủ: invokeExact, invoke và adaptation

Sau khi tìm được getter/setter, **handle.type()** là nguồn chính xác để biết các tham số được yêu cầu.

~~~java
// stockGet.type() == (Item)int
int exact = (int) stockGet.invokeExact(item);

// Cách gọi sau yêu cầu (Item)long và sẽ không khớp:
// long wrong = (long) stockGet.invokeExact(item);
~~~

Đây là đoạn minh họa lấy **stockGet** và **item** từ ví dụ hoàn chỉnh. Với **invokeExact**:

- **Receiver type** phải khớp với kiểu được handle yêu cầu; một cast tại call site có thể cần thiết khi receiver đang khai báo bằng lớp cha.
- **Primitive và wrapper** không hoán đổi tự động, ví dụ int khác Integer.
- **Kiểu kết quả cũng phải khớp**, không chỉ số lượng và kiểu tham số.
- **Setter** có kiểu trả void, nên lời gọi dưới dạng statement là phù hợp; không cố ép setter thành giá trị trả về.

**MethodHandle.invoke(...)** cho phép một số adaptation được định nghĩa bởi API, tương tự phép biến đổi qua **asType(...)**; không bảo đảm hỗ trợ mọi kiểu ép/chuyển. Khi một adaptation không hợp lệ, có thể phát sinh **WrongMethodTypeException**; các lỗi ép reference hoặc unboxing có thể xuất hiện tại runtime. Đừng dùng adaptation để che giấu việc chọn sai field type trong lệnh lookup.

Ví dụ khi API ứng dụng cần trả về Integer:

~~~java
MethodHandle boxedGetter = stockGet.asType(
        java.lang.invoke.MethodType.methodType(
                Integer.class, Item.class));

// boxedGetter.type() == (Item)Integer
Integer stockValue = (Integer) boxedGetter.invokeExact(item);
~~~

Đoạn minh họa này chỉ hoạt động vì adaptation **int → Integer** được phép. **stockGet** ban đầu vẫn có chữ ký **(Item)int**; **asType** trả handle adapter khác. **asType** không tự chuyển một setter field thành getter hoặc thay đổi loại field mà nó truy cập.

## 8. Kết hợp với reflection: unreflectGetter và unreflectSetter

Khi đã có đối tượng **java.lang.reflect.Field**, có thể chuyển nó thành MethodHandle bằng:

~~~java
java.lang.reflect.Field field =
        Item.class.getDeclaredField("stock");

MethodHandle reflectedGetter = lookup.unreflectGetter(field);
MethodHandle reflectedSetter = lookup.unreflectSetter(field);
~~~

Đây là đoạn **minh họa bên trong lớp FieldLookupDemo**, dùng biến **lookup** đã có quyền đọc/ghi private field của Item. Nếu chạy bên ngoài ngữ cảnh đó, phải có Lookup có quyền phù hợp. **unreflectGetter** và **unreflectSetter** xét quyền truy cập của **Field** và Lookup; biết Field không có nghĩa tự động vượt qua quyền truy cập.

**Khi chọn API:**

- Đã biết **Class**, **tên field**, **Class kiểu field** → ưu tiên **findGetter/findSetter** vì đơn giản, không cần tạo đối tượng Field trung gian.
- Đã có **Field** từ hoạt động quét metadata/reflection → **unreflectGetter/unreflectSetter** có thể kết nối sang MethodHandle.
- Muốn gọi **getX()/setX(...)** là những **phương thức** → sử dụng **findVirtual/unreflect** cho Method thay vì API cho field.

**Cẩn thận với final:** **unreflectSetter** có những ngoại lệ rất hẹp liên quan đến khả năng ghi của Field và quy tắc runtime; không nên coi nó là cách ghi hợp lệ vào mọi final field. **Static final** không có setter khả dụng thông thường. Khi cần đối tượng bất biến mới, tạo đối tượng mới qua constructor/factory thay vì cưỡng ép sửa field.

## 9. Khi nào nên dùng VarHandle thay cho field MethodHandle?

Từ **Java 9**, **java.lang.invoke.VarHandle** cung cấp mô hình truy cập biến phong phú hơn. Nếu cần **compare-and-set**, **get-and-add** hoặc điều khiển rõ hơn ngữ nghĩa memory ordering ở mức field, VarHandle thường phù hợp hơn getter/setter MethodHandle thuần.

API tra cứu tương ứng:

~~~java
java.lang.invoke.VarHandle stock =
        lookup.findVarHandle(Item.class, "stock", int.class);
java.lang.invoke.VarHandle stage =
        lookup.findStaticVarHandle(Item.class, "stage", String.class);
~~~

Đoạn này dùng chính **Item** và **lookup** trong chương trình mẫu, và cần import hoặc tên đầy đủ của VarHandle. Nó minh họa **VarHandle có variable type và coordinate types**, không có MethodType trả về void như setter MethodHandle.

Một thao tác nguyên tử trên trường số nguyên có thể viết:

~~~java
// Item item lấy từ chương trình mẫu; stock là VarHandle cho int stock.
int before = (int) stock.get(item);
int oldValue = (int) stock.getAndAdd(item, 1);
boolean changed = stock.compareAndSet(item, oldValue + 1, 20);
~~~

Đây là đoạn minh họa chứ không thuộc stdout của chương trình chính. **getAndAdd** là phép cộng nguyên tử khi access mode được hỗ trợ cho loại biến; **compareAndSet** chỉ thành công khi giá trị hiện tại khớp kỳ vọng. Việc **đọc before rồi tính toán và set** theo hai lệnh riêng lẻ không tự nhiên trở thành thao tác nguyên tử. Đối với concurrency, phải chọn mode và thiết kế đồng bộ theo yêu cầu; các kiểu field, finality và access mode có giới hạn riêng.

Không cần chuyển toàn bộ code truy cập field sang VarHandle: nếu chỉ cần đọc/ghi trực tiếp đã được phép, MethodHandle getter/setter vẫn là API hiện hành và hữu ích. VarHandle là lựa chọn khi bài toán đòi hỏi thao tác trên **biến** cùng ngữ nghĩa đồng bộ/atomic rõ ràng.

## 10. Lỗi thường gặp và cách phân biệt

| Tình huống | Kết quả/hệ quả điển hình | Cách sửa |
| --- | --- | --- |
| Tra cứu field **stock** với **long.class** khi field là int | **NoSuchFieldException** tại lookup | Dùng **int.class** đúng kiểu khai báo |
| Tra cứu field instance bằng **findStaticGetter** hoặc static bằng **findGetter** | **IllegalAccessException** vì loại truy cập không phù hợp | Dùng đúng API instance/static |
| Dùng publicLookup tìm field private | **IllegalAccessException** | Truy cập qua API public hoặc Lookup có quyền thật sự |
| Dùng Lookup không đủ quyền trong JPMS | **IllegalAccessException** | Kiểm tra module exports/opens và quyền Lookup |
| Tạo setter cho field final | **IllegalAccessException** với direct setter | Giữ bất biến, tạo object mới |
| Dùng tên phương thức **getName** cho **findGetter** | Field đó không tồn tại, thường **NoSuchFieldException** | Tra cứu **name** hoặc gọi phương thức qua **findVirtual** |
| Truyền **Integer.class** cho field khai báo int | Sai field type, thường **NoSuchFieldException** | Dùng **int.class**, adapt handle sau |
| Gọi **invokeExact** với kiểu trả khác kiểu getter | **WrongMethodTypeException** | Kiểm tra handle.type(), cast đúng kiểu |
| Gọi getter instance mà receiver là null | **NullPointerException** khi truy cập field | Bảo đảm đối tượng receiver không null |
| Sửa field có invariant nhưng bỏ qua setter method | Domain state có thể không hợp lệ | Tôn trọng API/validation của lớp |
| Đưa private field handle cho plugin không tin cậy | Có thể lộ quyền truy cập nội bộ | Giới hạn việc chia sẻ Lookup/MethodHandle |
| Cập nhật **counter = get() + 1** song song | Read-modify-write không atomic | Dùng đồng bộ thích hợp, VarHandle atomic mode hoặc cấu trúc concurrency |
| Nhầm lỗi tại lookup với lỗi tại invocation | Bắt sai loại exception, khó debug | Phân biệt NoSuchFieldException/IllegalAccessException với WrongMethodTypeException và lỗi runtime khác |

### Đọc lỗi theo đúng giai đoạn

**Lúc tra cứu:**

- **NoSuchFieldException**: không tìm được field với đúng tên và kiểu trong phép tìm kiếm; có thể do typo hoặc field type thay đổi.
- **IllegalAccessException**: field tồn tại nhưng quyền/loại truy cập/finality không cho phép handle được yêu cầu.
- **NullPointerException** có thể phát sinh khi tham số **refc/name/type** null.

**Lúc gọi handle:**

- **WrongMethodTypeException**: chữ ký gọi không thích hợp với handle, đặc biệt với **invokeExact**.
- **NullPointerException**: receiver null hoặc conversion cần unbox null trong trường hợp được adapt.
- **ClassCastException**: một phép cast/chuyển reference không hợp lệ khi gọi hoặc adapter hoạt động.
- Các lỗi do môi trường/runtime hoặc class initialization có thể xuất hiện; đừng bắt mọi Throwable rồi mặc định rằng đó là lỗi “không tìm thấy field”.

## 11. Quy trình ứng dụng an toàn và dễ kiểm thử

Khi xây dựng một mapper/framework đọc field theo metadata:

1. **Xác định field trước**: lớp mục tiêu, tên thực tế, kiểu khai báo và field là instance hay static. Không đoán tên theo quy ước accessor.
2. **Chọn Lookup với quyền hợp lệ**: chỉ yêu cầu private access nếu thiết kế module và quyền của caller cho phép.
3. **Tạo đúng getter/setter**: dùng **findGetter/findSetter** hoặc các bản static; không thử tạo setter cho final.
4. **Đọc handle.type()** để kiểm chứng chữ ký thực, kể cả receiver và primitive/wrapper.
5. **Cache handle khi phù hợp**: tránh lặp lại lookup trong đường xử lý nóng; cache theo lớp/name/type và ngữ cảnh class loader phù hợp, không biến một handle có quyền thành API công khai ngoài ý muốn.
6. **Gọi đúng kiểu**: ưu tiên **invokeExact** khi biết chữ ký, hoặc dùng adaptation có kiểm soát khi cần.
7. **Bảo vệ domain invariant**: nếu getter/setter method chứa validation, không thay bằng field access chỉ vì nhanh hơn.
8. **Kiểm thử cả đường lỗi**: sai field name/type, quyền truy cập, static/instance, final, receiver null, call-site type sai và concurrency nếu dữ liệu dùng chung.

### Câu hỏi tự kiểm tra

1. **findGetter(Product.class, "price", BigDecimal.class)** tìm phương thức getPrice() hay field price? → **Field price**; để gọi getPrice(), dùng lookup cho **phương thức**.
2. **Instance getter của field int count** nhận đối số nào và trả gì? → Nhận receiver, trả int: **(R)int**.
3. **Instance setter của field String name** có chữ ký gì? → **(R,String)void**.
4. **Static getter có nhận receiver không?** → Không: chữ ký **()T**.
5. **Field khai báo int nhưng yêu cầu Long.class thì sao?** → Tìm field sai kiểu, **NoSuchFieldException**; không phải conversion hợp lệ ở bước lookup.
6. **Có thể lấy getter cho final field không?** → Có, nếu có quyền đọc; setter direct thông thường bị từ chối.
7. **privateLookupIn có luôn lấy được mọi private field của module khác không?** → Không; phải đáp ứng quyền và quy tắc modules/opens.
8. **Khi nào VarHandle đáng dùng hơn getter/setter MethodHandle?** → Khi cần access modes, CAS hoặc phép cập nhật nguyên tử trên biến.

**Ghi nhớ:** **Lookup.findGetter/findSetter** tạo MethodHandle đọc/ghi **field** theo đúng **Class, tên, kiểu và quyền truy cập**. Chữ ký của getter/setter bao gồm receiver ở instance field, không có receiver ở static field. **MethodHandle.type()** và **invokeExact** giúp kiểm soát kiểu tại call site; **final**, **private**, module access và invariant nghiệp vụ vẫn phải được tôn trọng.

**Tài liệu API đang được duy trì:**

- [Java SE 17 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html) — đặc tả các phương thức findGetter, findSetter, static variants.
- [Java SE 26 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html) — reference mới, quy tắc quyền và unreflectGetter/unreflectSetter.
- [Java SE 26 — MethodHandle](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandle.html) — invokeExact, invoke và MethodType.
- [Java SE 26 — VarHandle](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/VarHandle.html) — access modes và các phép nguyên tử.
