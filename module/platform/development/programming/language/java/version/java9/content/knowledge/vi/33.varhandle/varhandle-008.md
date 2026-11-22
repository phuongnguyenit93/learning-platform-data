# getAndSet, getAndAdd và các phép cập nhật bit với VarHandle

## Mục tiêu

Sau bài học này, bạn có thể:

- Dùng các access mode \`getAndSet\`, \`getAndAdd\` và \`getAndBitwiseOr/And/Xor\` để cập nhật một biến nguyên tử.
- Hiểu rằng các method này trả về giá trị trước khi cập nhật.
- Chọn phép OR, AND hoặc XOR để đặt, xóa và đảo bit trong một cờ trạng thái.
- Phân biệt một thao tác read-modify-write nguyên tử với chuỗi đọc rồi ghi thông thường.
- Chọn memory ordering mặc định, Acquire hoặc Release theo giao thức đồng bộ hóa.
- Tạo VarHandle đúng kiểu và xử lý access mode không được hỗ trợ.

## 1. VarHandle và atomic read-modify-write

\`VarHandle\` là một tham chiếu có kiểu mạnh đến một biến hoặc một nhóm biến. Nó có thể đại diện cho field instance, static field, phần tử array và một số dạng vùng nhớ được API hỗ trợ.

Java 9 đưa VarHandle vào JDK để cung cấp các thao tác đọc, ghi và cập nhật nguyên tử với nhiều mức memory ordering. Trong bài này, ta tập trung vào các thao tác đọc-sửa-ghi:

- Đọc giá trị hiện tại.
- Tính giá trị mới từ giá trị hiện tại và một tham số.
- Ghi giá trị mới như một thao tác nguyên tử.
- Trả về giá trị cũ đã được đọc trong chính thao tác đó.

Đây là một thao tác read-modify-write (RMW). Hai thread cùng gọi RMW trên một biến sẽ không ghi đè lẫn nhau như cách làm riêng rẽ \`get()\` rồi \`set()\`.

Ví dụ không an toàn khi có nhiều thread:

~~~java
int old = (int) COUNT.getVolatile(state);
COUNT.setVolatile(state, old + 1);
~~~

Hai thread có thể cùng đọc một giá trị rồi cùng ghi kết quả giống nhau, làm mất một lần tăng. Dùng \`getAndAdd\` để gộp việc đọc, cộng và ghi thành một thao tác nguyên tử:

~~~java
int old = (int) COUNT.getAndAdd(state, 1);
~~~

Mỗi lần gọi cập nhật biến đúng một lần. Giá trị trả về là giá trị trước khi cập nhật, không phải giá trị mới.

## 2. getAndSet: thay thế giá trị và nhận lại giá trị cũ

\`getAndSet\` đặt biến thành giá trị mới và trả về giá trị cũ:

~~~java
String previous = (String) STATUS.getAndSet(state, "READY");
~~~

Nếu \`STATUS\` đang giữ \`"NEW"\`, sau lời gọi:

- Giá trị trả về là \`"NEW"\`.
- Giá trị hiện tại của field là \`"READY"\`.

Method hữu ích cho các thao tác chuyển trạng thái, thay thế tham chiếu hoặc lấy giá trị trước khi cài đặt giá trị mới.

Với field tham chiếu, thao tác chỉ thay thế tham chiếu một cách nguyên tử. Nó không làm cho object được tham chiếu trở nên thread-safe và không đồng bộ các field bên trong object đó.

Ví dụ dùng \`getAndSet\` để nhận quyền xử lý một cờ boolean:

~~~java
boolean wasRunning = (boolean) RUNNING.getAndSet(state, true);
if (!wasRunning) {
    startWorker();
}
~~~

Việc cập nhật cờ là nguyên tử. Tuy nhiên, nếu nhiều thread cùng cần phối hợp cả việc đổi cờ và khởi chạy một tài nguyên khác, hãy thiết kế rõ ai chịu trách nhiệm khởi chạy và xử lý lỗi sau khi giành được quyền.

## 3. getAndAdd: cộng nguyên tử

\`getAndAdd\` cộng một giá trị vào biến và trả về giá trị trước khi cộng:

~~~java
int previous = (int) COUNT.getAndAdd(state, 5);
~~~

Nếu \`COUNT\` ban đầu bằng 10, sau lời gọi:

- \`previous\` bằng 10.
- \`COUNT\` bằng 15.

Access mode này phù hợp cho counter, sequence number, số lượng công việc hoặc bộ tích lũy cần cập nhật từ nhiều thread.

VarHandle hỗ trợ numeric atomic update cho các kiểu số nguyên thủy và dấu phẩy động mà handle cho phép, gồm \`byte\`, \`short\`, \`char\`, \`int\`, \`long\`, \`float\` và \`double\`. Không áp dụng \`getAndAdd\` cho field tham chiếu hoặc \`boolean\`.

Với kiểu có miền giá trị hữu hạn, hãy cân nhắc overflow. Ví dụ, phép cộng trên \`int\` không tự ném exception khi vượt \`Integer.MAX_VALUE\`; kết quả tuân theo phép toán số nguyên của Java và có thể quay vòng.

Với \`float\` và \`double\`, cập nhật vẫn là nguyên tử, nhưng kết quả số học vẫn chịu quy tắc độ chính xác dấu phẩy động. Không giả định phép cộng dấu phẩy động có tính kết hợp như số nguyên.

## 4. getAndBitwiseOr, getAndBitwiseAnd và getAndBitwiseXor

Ba access mode bitwise cập nhật giá trị hiện tại bằng một mask. Mỗi method trả về giá trị trước khi cập nhật.

| Method | Công thức | Cách dùng thường gặp |
|---|---|---|
| \`getAndBitwiseOr(mask)\` | \`old | mask\` | Đặt các bit |
| \`getAndBitwiseAnd(mask)\` | \`old & mask\` | Giữ một tập bit, xóa các bit còn lại |
| \`getAndBitwiseXor(mask)\` | \`old ^ mask\` | Đảo các bit được chọn |

Giả sử một field \`flags\` lưu quyền đọc và ghi:

~~~java
static final int READ = 1;   // 0001
static final int WRITE = 2;  // 0010
~~~

### 4.1. OR để bật bit

~~~java
int previous = (int) FLAGS.getAndBitwiseOr(state, READ | WRITE);
~~~

OR với mask đặt các bit tương ứng thành 1 và giữ nguyên những bit khác. Nếu cờ ban đầu bằng 0, giá trị mới là 3.

### 4.2. AND để xóa bit

Để xóa riêng bit READ, dùng mask đảo của READ:

~~~java
int previous = (int) FLAGS.getAndBitwiseAnd(state, ~READ);
~~~

AND với \`~READ\` làm bit READ thành 0 và giữ nguyên các bit khác. Nếu cờ đang là \`READ | WRITE\`, kết quả mới chỉ còn WRITE.

Cần phân biệt cách này với \`getAndBitwiseAnd(state, READ)\`: mask READ chỉ giữ bit READ và xóa mọi bit khác.

### 4.3. XOR để đảo bit

~~~java
int previous = (int) FLAGS.getAndBitwiseXor(state, WRITE);
~~~

XOR với mask đảo trạng thái các bit có giá trị 1 trong mask. Bit đang là 0 thành 1; bit đang là 1 thành 0. Dùng XOR khi thao tác thực sự có ý nghĩa toggle, không dùng để đặt một bit về trạng thái cố định.

Các phép bitwise này cũng có dạng access mode cho field \`boolean\`. Khi variable type là \`boolean\`, OR, AND và XOR được thực hiện như phép logic tương ứng.

## 5. Giá trị trả về luôn là giá trị trước cập nhật

Các method có tên \`getAnd...\` trả về giá trị cũ:

~~~java
int old = (int) COUNT.getAndAdd(state, 2);
~~~

Nếu giá trị ban đầu là 7, \`old\` bằng 7 và giá trị mới bằng 9.

Nếu cần tính giá trị mới của chính lần cập nhật đó, với phép cộng có thể suy ra \`old + delta\`, và với phép bitwise có thể suy ra \`old | mask\`, \`old & mask\` hoặc \`old ^ mask\`. Nhưng một thread khác vẫn có thể cập nhật biến ngay sau thao tác của bạn. Vì vậy, một lần đọc riêng sau đó có thể thấy giá trị mới hơn nữa.

Không viết:

~~~java
COUNT.getAndAdd(state, 1);
int newValue = (int) COUNT.getVolatile(state);
~~~

rồi cho rằng \`newValue\` chắc chắn là kết quả riêng của lần gọi vừa rồi. Nó là giá trị hiện tại tại thời điểm lần đọc thứ hai diễn ra.

Nếu cần một quyết định nguyên tử dựa trên điều kiện của giá trị hiện tại, hãy cân nhắc \`compareAndSet\` hoặc \`compareAndExchange\` với vòng lặp CAS được thiết kế đúng. Các thao tác \`getAnd...\` phù hợp khi phép cập nhật đã được xác định trực tiếp bởi toán hạng.

## 6. Tạo VarHandle cho đúng biến

Với field instance, dùng \`MethodHandles.Lookup.findVarHandle\`:

~~~java
VarHandle countHandle = MethodHandles.lookup().findVarHandle(
        State.class, "count", int.class);
~~~

Khi gọi access mode, truyền object chứa field trước các tham số cập nhật:

~~~java
int old = (int) countHandle.getAndAdd(state, 1);
~~~

Với static field, dùng \`findStaticVarHandle\`; không truyền receiver object:

~~~java
VarHandle totalHandle = MethodHandles.lookup().findStaticVarHandle(
        State.class, "total", long.class);

long oldTotal = (long) totalHandle.getAndAdd(1L);
~~~

Với phần tử array, dùng factory method:

~~~java
VarHandle elements =
        MethodHandles.arrayElementVarHandle(int[].class);

int[] values = new int[4];
int oldElement = (int) elements.getAndAdd(values, 2, 10);
~~~

VarHandle có kiểu biến và kiểu tọa độ. Số lượng, thứ tự và kiểu tham số phải khớp với handle. Vì các access mode method là signature-polymorphic, hãy dùng đúng kiểu đối số và kiểu ép kết quả:

~~~java
int old = (int) countHandle.getAndAdd(state, 1);
String previous = (String) statusHandle.getAndSet(state, "READY");
~~~

## 7. Memory ordering: mặc định, Acquire và Release

Các access mode cập nhật nguyên tử có nhiều biến thể memory ordering.

| Nhóm | Ví dụ | Ý nghĩa chính |
|---|---|---|
| Mặc định | \`getAndSet\`, \`getAndAdd\`, \`getAndBitwiseOr\` | Memory effects kiểu volatile cho phần đọc và ghi |
| Acquire | \`getAndSetAcquire\`, \`getAndAddAcquire\` | Phần đọc có acquire; phần ghi có plain semantics |
| Release | \`getAndSetRelease\`, \`getAndAddRelease\` | Phần đọc có plain semantics; phần ghi có release |

Các biến thể \`Acquire\` và \`Release\` cũng có cho các phép cập nhật bit.

Dùng dạng mặc định trước nếu bạn cần hành vi volatile và chưa có một giao thức memory ordering cụ thể. Dạng mặc định vừa thực hiện cập nhật nguyên tử vừa có memory effects kiểu volatile.

Acquire và Release cho phép xây dựng giao thức đồng bộ hóa nhẹ hơn:

- Acquire đảm bảo các thao tác đọc/ghi sau đó không bị sắp xếp trước thao tác acquire và có thể quan sát dữ liệu được công bố bởi release tương ứng.
- Release đảm bảo các thao tác đọc/ghi trước đó không bị sắp xếp sau thao tác release.

Các biến thể này vẫn thực hiện update nguyên tử. Khác biệt nằm ở quan hệ ordering và visibility giữa các thao tác trên nhiều biến. Chỉ dùng chúng khi bạn hiểu quan hệ happens-before mà chương trình cần; không đổi sang Acquire/Release chỉ vì nghĩ rằng chúng luôn nhanh hơn.

Một điểm dễ nhầm: memory ordering được chọn bởi access mode của VarHandle. Modifier \`volatile\` trên khai báo field không thay đổi semantics của access mode đang gọi. Trộn \`get\` plain với \`getVolatile\`, hoặc trộn các access mode có ordering khác nhau trên cùng biến, cần được thiết kế cẩn thận.

## 8. Ví dụ hoàn chỉnh: cập nhật trạng thái, counter và bit flags

Tạo file **VarHandleAtomicUpdatesDemo.java**:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class VarHandleAtomicUpdatesDemo {

    private static final int READ = 1;
    private static final int WRITE = 2;

    private static final class State {
        volatile String status = "NEW";
        volatile int count;
        volatile int flags;
    }

    private static final VarHandle STATUS;
    private static final VarHandle COUNT;
    private static final VarHandle FLAGS;

    static {
        try {
            MethodHandles.Lookup lookup = MethodHandles.lookup();
            STATUS = lookup.findVarHandle(
                    State.class, "status", String.class);
            COUNT = lookup.findVarHandle(
                    State.class, "count", int.class);
            FLAGS = lookup.findVarHandle(
                    State.class, "flags", int.class);
        } catch (ReflectiveOperationException error) {
            throw new ExceptionInInitializerError(error);
        }
    }

    public static void main(String[] args) throws Exception {
        State state = new State();

        String oldStatus =
                (String) STATUS.getAndSet(state, "READY");
        System.out.println("status previous = " + oldStatus);
        System.out.println("status current = "
                + STATUS.getVolatile(state));

        int oldCount = (int) COUNT.getAndAdd(state, 5);
        System.out.println("count previous = " + oldCount);
        System.out.println("count current = " + COUNT.getVolatile(state));

        int beforeOr =
                (int) FLAGS.getAndBitwiseOr(state, READ | WRITE);
        System.out.println("flags before OR = " + beforeOr);
        System.out.println("flags after OR = " + FLAGS.getVolatile(state));

        int beforeXor =
                (int) FLAGS.getAndBitwiseXor(state, WRITE);
        System.out.println("flags before XOR = " + beforeXor);
        System.out.println("flags after XOR = " + FLAGS.getVolatile(state));

        int beforeAnd =
                (int) FLAGS.getAndBitwiseAnd(state, ~READ);
        System.out.println("flags before AND = " + beforeAnd);
        System.out.println("flags after AND = " + FLAGS.getVolatile(state));

        ExecutorService executor = Executors.newFixedThreadPool(4);
        try {
            List<Future<?>> tasks = new ArrayList<>();

            for (int worker = 0; worker < 4; worker++) {
                tasks.add(executor.submit(() -> {
                    for (int index = 0; index < 1000; index++) {
                        COUNT.getAndAdd(state, 1);
                    }
                }));
            }

            for (Future<?> task : tasks) {
                task.get();
            }
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }

        System.out.println("count after concurrent adds = "
                + COUNT.getVolatile(state));
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 -Xlint:all -d out VarHandleAtomicUpdatesDemo.java
java -cp out VarHandleAtomicUpdatesDemo
~~~

Output chính xác:

~~~text
status previous = NEW
status current = READY
count previous = 0
count current = 5
flags before OR = 0
flags after OR = 3
flags before XOR = 3
flags after XOR = 1
flags before AND = 1
flags after AND = 0
count after concurrent adds = 4005
~~~

Bốn worker cùng thực hiện 1.000 lần cộng vào một field. Counter bắt đầu ở 5 và kết thúc ở 4.005. Mỗi lần cộng dùng một \`getAndAdd\` nguyên tử, nên các lần tăng không bị mất do hai thread cùng đọc rồi ghi đè kết quả.

Ví dụ cũng cho thấy \`getAndSet\` thay trạng thái, OR bật hai bit, XOR đảo bit WRITE và AND với \`~READ\` xóa bit READ.

## 9. Kiểm tra access mode và xử lý lỗi

Không phải mọi VarHandle đều hỗ trợ mọi access mode. Ví dụ, handle trỏ đến field chỉ đọc như \`final\` không hỗ trợ các thao tác ghi hoặc cập nhật nguyên tử.

Có thể kiểm tra trước:

~~~java
if (!COUNT.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD)) {
    throw new UnsupportedOperationException("GET_AND_ADD is unavailable");
}
~~~

Các lỗi thường gặp:

| Lỗi | Nguyên nhân thường gặp |
|---|---|
| \`UnsupportedOperationException\` | Handle không hỗ trợ access mode, chẳng hạn biến chỉ đọc |
| \`WrongMethodTypeException\` | Kiểu hoặc số lượng đối số tại call site không khớp kiểu của handle |
| \`ClassCastException\` | Giá trị tham chiếu không tương thích với kiểu biến |
| \`NullPointerException\` | Receiver hoặc đối số tọa độ cần thiết là null |
| \`NoSuchFieldException\` | Tên field hoặc kiểu field khi lookup không đúng |
| \`IllegalAccessException\` | Lookup không có quyền truy cập field |

Nếu tạo handle cho field private, quyền truy cập được kiểm tra lúc tạo VarHandle. Handle sau đó là một capability để truy cập biến đó; không chia sẻ handle nhạy cảm cho code không tin cậy.

## 10. Giới hạn của thao tác nguyên tử

Atomicity áp dụng cho một biến được VarHandle trỏ tới và một access mode invocation. Nó không tự tạo transaction trên nhiều field.

Ví dụ, nếu cần cập nhật đồng thời \`balance\` và \`version\` sao cho một invariant luôn đúng, hai lời gọi \`getAndAdd\` riêng rẽ không làm toàn bộ cặp thay đổi trở thành nguyên tử. Hãy dùng lock, một trạng thái bất biến được thay thế bằng CAS, hoặc một giao thức đồng bộ hóa phù hợp.

Ngoài ra:

- \`getAndSet\` không bảo vệ nội dung mutable của object được gán.
- \`getAndAdd\` không ngăn overflow của kiểu số.
- \`getAndBitwiseXor\` là thao tác toggle; hai lần toggle cùng mask sẽ đưa bit về trạng thái ban đầu.
- Giá trị trả về là snapshot cũ của chính thao tác, không phải giá trị hiện tại được đảm bảo sau khi method trả về nếu thread khác tiếp tục cập nhật.
- Không dùng một lần đọc plain để quan sát dữ liệu được công bố qua một giao thức volatile/acquire-release khác.

## 11. Lỗi thường gặp

### Tách get và set khi cần một phép cập nhật nguyên tử

Một cặp đọc/ghi riêng lẻ có thể làm mất cập nhật khi nhiều thread cạnh tranh. Dùng đúng access mode \`getAnd...\`.

### Nghĩ method trả về giá trị mới

Các method \`getAndSet\`, \`getAndAdd\` và \`getAndBitwise...\` trả về giá trị trước cập nhật. Nếu cần giá trị mới, hãy tính từ giá trị cũ hoặc thiết kế API phù hợp.

### Dùng AND với mask sai để xóa bit

Muốn xóa một bit, dùng mask có bit đó bằng 0, thường là \`~FLAG\`. AND trực tiếp với FLAG sẽ xóa tất cả bit không nằm trong FLAG.

### Dùng XOR để đặt bit cố định

XOR đảo bit. Nếu bit có thể đang là 1, thao tác XOR sẽ tắt nó. Dùng OR để bảo đảm bật bit; dùng AND với mask phù hợp để xóa.

### Nhầm thao tác nguyên tử trên một field với transaction

Nhiều access mode không tự đồng bộ một nhóm field. Dùng lock hoặc CAS protocol nếu invariant trải qua nhiều biến.

### Chọn Acquire/Release mà không xác định happens-before

Acquire/Release có ordering khác dạng volatile mặc định. Chỉ chọn chúng khi giao thức công bố và tiêu thụ dữ liệu đã được xác định rõ.

### Cho rằng modifier volatile quyết định semantics của mọi lần truy cập VarHandle

Access mode được gọi quyết định memory effects. Trộn các access mode khác nhau trên cùng biến cần phân tích theo Java Memory Model.

### Truyền sai kiểu đối số

VarHandle access mode có kiểu call-site cụ thể. Dùng đúng primitive, receiver và kiểu trả về; kiểm tra \`accessModeType\` nếu cần chẩn đoán.

## 12. Checklist

- [ ] Đã chọn đúng field hoặc array element và tạo VarHandle đúng kiểu.
- [ ] Đã dùng \`getAndSet\` khi cần thay thế giá trị và nhận giá trị cũ.
- [ ] Đã dùng \`getAndAdd\` cho phép cộng nguyên tử.
- [ ] Đã dùng OR để bật bit, AND với mask phù hợp để xóa bit và XOR để đảo bit.
- [ ] Đã nhớ các method \`getAnd...\` trả về giá trị trước cập nhật.
- [ ] Đã tính đến overflow và độ chính xác số học.
- [ ] Đã chọn memory ordering phù hợp; mặc định volatile khi chưa có lý do dùng Acquire/Release.
- [ ] Đã kiểm tra access mode có được hỗ trợ khi cần tính tương thích.
- [ ] Đã không dựa vào một thao tác nguyên tử để bảo vệ invariant trên nhiều field.
- [ ] Đã biên dịch và chạy ví dụ bằng Java 9+.

## 13. Tài liệu tham khảo

- [Java SE 17 API: VarHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html)
- [Java SE 17 API: MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)

