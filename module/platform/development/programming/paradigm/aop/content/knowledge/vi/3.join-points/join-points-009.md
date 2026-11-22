# Những thao tác không thuộc mô hình join point của công cụ đang dùng

> **Mục tiêu:** Hiểu vì sao một hoạt động xảy ra trong chương trình nhưng không nhất thiết là **join point** mà một công cụ lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP) nhận diện được; phân biệt giới hạn của **mô hình join point**, **pointcut**, **weaving** và **đường thực thi**; tự xác định vùng được can thiệp, vùng không thể can thiệp, cũng như cách chọn một cơ chế phù hợp để không bỏ sót hành vi quan trọng.

## 1. Một hành vi có thật trong chương trình chưa chắc là join point

Một chương trình Java có thể tạo đối tượng, gọi phương thức, đọc/ghi trường, chuyển luồng thực thi, ném và bắt ngoại lệ, đồng bộ hóa, gọi mã native, gửi yêu cầu ra mạng, hoặc thay đổi dữ liệu ở hệ thống bên ngoài. Tất cả đều là những hoạt động thật. Nhưng **không phải mọi hoạt động đều là join point của công cụ AOP đang dùng**.

Trong AOP, **join point** là một điểm hoặc sự kiện thuộc mô hình thực thi mà cơ chế AOP có khả năng xác định và cho phép kết hợp hành vi bổ sung (*advice*), khi mã liên quan nằm trong phạm vi xử lý của cơ chế.

Điểm phân biệt then chốt:

- **Hoạt động thực tế:** bất kỳ công việc nào hệ thống thực hiện.
- **Join point theo mô hình:** loại điểm/sự kiện mà công cụ AOP **định nghĩa là có thể can thiệp**.
- **Join point được pointcut chọn:** điểm thuộc mô hình và thỏa biểu thức lựa chọn.
- **Join point được weaving/đường thực thi bao phủ:** điểm mà cơ chế kết hợp aspect **thật sự** có khả năng quan sát trong chương trình đang chạy.
- **Advice đã chạy:** kết quả quan sát được khi mọi điều kiện về mô hình, lựa chọn, triển khai và luồng thực thi đều được đáp ứng.

Ví dụ, một cơ chế chỉ chặn **lời gọi phương thức qua proxy của giao diện** sẽ không tự biến câu lệnh gán trường `order.status = "PAID"` thành join point mà proxy nhìn thấy. Việc mở rộng pointcut từ “một phương thức” thành “mọi phương thức” **không làm cho gán trường trở thành lời gọi phương thức qua proxy**.

Ngược lại, một mô hình AOP có hỗ trợ join point kiểu **field set** có thể can thiệp vào phép gán trường theo điều kiện và phạm vi weaving phù hợp. Vì vậy, ta không thể kết luận chung rằng “AOP không chặn được gán trường”; kết luận đúng phải là **“cơ chế cụ thể đang xét có hỗ trợ loại join point đó không?”**.

## 2. Bốn lớp quyết định khả năng can thiệp

Có thể đánh giá một hoạt động từ ngoài vào trong theo bốn câu hỏi:

```text
Hoạt động cần quan sát
         |
         v
(1) Loại hoạt động thuộc JOIN POINT MODEL?
         |
         v
(2) POINTCUT có chọn đúng điểm đó?
         |
         v
(3) Mã/đường thực thi nằm trong WEAVING SCOPE?
         |
         v
(4) Khi chạy, sự kiện có đi qua cơ chế can thiệp
    và thỏa những điều kiện động?
         |
         v
Advice có thể được kích hoạt
```

Đây là **mô hình phân tích khái niệm**. Một công cụ thực tế có thể thực hiện các bước theo thứ tự khác hoặc tối ưu một số bước, nhưng bốn câu hỏi vẫn hữu ích để chẩn đoán.

| Lớp | Câu hỏi | Ví dụ nguyên nhân không chạy advice |
|---|---|---|
| **Join point model** | Công cụ có hỗ trợ *loại* điểm này? | Chỉ hỗ trợ method invocation qua proxy, không hỗ trợ field write |
| **Pointcut** | Điểm có thỏa điều kiện lựa chọn? | Pointcut chỉ chọn `save*`, còn phương thức là `commit()` |
| **Weaving scope** | Mã liên quan đã nằm trong phạm vi cơ chế xử lý? | Một thư viện/mô-đun bị loại khỏi phạm vi weaving |
| **Runtime path / dynamic match** | Lần chạy cụ thể có đi qua ranh giới can thiệp và thỏa điều kiện? | Lời gọi trực tiếp tới đối tượng đích thay vì đi qua proxy; đối số không khớp |

**Điều kiện tiên quyết:** Nếu một hoạt động **không thuộc join point model**, không có pointcut nào trong **chính mô hình đó** có thể chọn nó. Muốn bao phủ hành vi, có thể cần thay đổi ranh giới thiết kế, một cơ chế weaving khác, một công cụ instrumentation khác hoặc quan sát sự kiện ở cấp phù hợp hơn.

## 3. Join point khác với từng câu lệnh và từng tác dụng phụ

Sai lầm phổ biến là suy luận: “Trong phương thức có 15 dòng mã, vậy chắc chắn có 15 join point.”

Join point không phải khái niệm đồng nghĩa với **dòng mã**, **biểu thức**, **instruction của JVM** hay **tác dụng phụ nghiệp vụ**.

Ví dụ:

```java
total += price;
order.status = "PAID";
System.out.println("Paid");
```

Đây là **mã minh họa rời**, không phải chương trình chạy độc lập. Trong đó:

- `total += price` thực hiện phép đọc/tính toán/gán tùy hình thức biến, nhưng không nhất thiết là join point của mọi AOP.
- `order.status = "PAID"` là phép ghi trường; chỉ có thể là join point kiểu **field set** nếu mô hình và phạm vi weaving hỗ trợ.
- `System.out.println(...)` có lời gọi phương thức. Một cơ chế hỗ trợ method call hoặc method execution **có thể** chọn nó, nhưng vẫn phải xét nơi mã được weaving và điều kiện pointcut.

Tương tự, thông tin “đã gửi email”, “đã ghi vào cơ sở dữ liệu” hay “đã hoàn tất giao dịch” **không tự là join point**. Đó là sự kiện hoặc kết quả có ý nghĩa nghiệp vụ; join point chỉ có thể đại diện cho một ranh giới kỹ thuật phù hợp nếu ta xác định và công cụ có khả năng quan sát.

## 4. Những loại join point mà các mô hình AOP có thể khác nhau

Không có một danh sách loại join point duy nhất áp dụng cho mọi cơ chế. Một mô hình AOP ở mức mã/bytecode có thể phong phú hơn một cơ chế dựa trên việc chuyển lời gọi qua đối tượng trung gian.

| Hoạt động trong chương trình | Khả năng trong các mô hình AOP | Câu hỏi phải xác minh |
|---|---|---|
| **Thực thi phương thức** (*method execution*) | Được nhiều mô hình hỗ trợ theo cách khác nhau | Chọn tại thân phương thức hay tại proxy bao quanh lời gọi? |
| **Lời gọi phương thức** (*method call*) | Có mô hình coi là join point riêng; có mô hình không | Có thể can thiệp tại **call site** không? |
| **Gọi constructor** (*constructor call*) | Chỉ một số cơ chế hỗ trợ | Cơ chế có xử lý biểu thức tạo thể hiện không? |
| **Thực thi constructor** (*constructor execution*) | Chỉ một số cơ chế hỗ trợ | Có nhận diện khi constructor thực sự chạy không? |
| **Khởi tạo đối tượng** (*initialization*) | Có mô hình định nghĩa riêng | Phạm vi khởi tạo và thứ tự advice là gì? |
| **Đọc trường** (*field get*) | Không phải khả năng mặc định của mọi công cụ | Có weaving được truy cập trường hay chỉ method? |
| **Ghi trường** (*field set*) | Tương tự field get | Phép gán trực tiếp, reflection hoặc access đặc biệt có được bao phủ? |
| **Xử lý ngoại lệ** (*exception handler*) | Một số mô hình có loại join point này | Can thiệp tại khối `catch` hay chỉ quanh method bị lỗi? |
| **Khởi tạo lớp, thao tác đồng bộ hóa hoặc sự kiện thấp hơn** | Tùy mô hình và phần mở rộng | Loại sự kiện có nằm trong đặc tả thực tế? |
| **Sự kiện ngoài tiến trình** (thông điệp, bản ghi DB, thay đổi filesystem do tiến trình khác) | Không tự trở thành join point của chương trình Java | Cần quan sát ở API, giao thức hoặc hệ thống sở hữu sự kiện? |

**Không nên học bảng như một tập quy tắc cứng** kiểu “field access luôn không thể chặn”. Cùng một hoạt động có thể là join point ở một mô hình nhưng không tồn tại trong mô hình khác.

### 4.1. Method call khác method execution

- **Call**: vị trí chương trình **phát sinh lời gọi**.
- **Execution**: việc phần thân của phương thức đích **được thực thi**.

Một phương thức có thể được gọi từ nhiều vị trí. Với weaving ở call site, quy tắc chọn caller có thể có ý nghĩa; với weaving ở execution, chính phương thức thực thi là trung tâm. Không nên giả định công cụ có cả hai loại chỉ vì nó “chặn được method”.

### 4.2. Phép đọc/ghi trường khác lời gọi getter/setter

```java
account.balance = 100;
int x = account.balance;
```

Nếu chương trình thay bằng `account.setBalance(100)` và `account.getBalance()`, ta đã **thay đổi ranh giới thiết kế** sang lời gọi method. Một công cụ chặn method có thể can thiệp vào getter/setter khi lời gọi đi qua cơ chế của nó, nhưng **không vì thế** can thiệp vào mọi phép gán/đọc trường trực tiếp khác.

Getter/setter cũng không mặc nhiên đại diện cho **mọi cách** thay đổi trạng thái: còn khởi tạo trong constructor, truy cập trực tiếp, reflection, hoặc những cơ chế khác được ngôn ngữ/runtime cho phép.

### 4.3. Exception handler khác “sau khi ném ngoại lệ”

Một advice chạy khi **method kết thúc bằng ngoại lệ** là hành vi quanh một join point method được lựa chọn. Nó không đồng nghĩa với join point tại **khối xử lý ngoại lệ**.

Nếu mô hình có join point *exception handler*, đó là một loại điểm riêng liên quan nơi ngoại lệ được xử lý. Việc “chặn mọi câu lệnh `throw`” lại là yêu cầu khác nữa và không tự suy ra từ việc hỗ trợ after-throwing advice.

## 5. Vì sao giới hạn của proxy hay bị hiểu thành giới hạn của AOP?

Trong Java, một cách tạo điểm can thiệp là đưa lời gọi qua **đối tượng trung gian**. Java Dynamic Proxy chuẩn cho phép tạo đối tượng triển khai một hoặc nhiều giao diện và xử lý các lời gọi **phương thức giao diện** qua `InvocationHandler`.

Nếu caller gọi qua proxy, handler có cơ hội can thiệp. Nếu caller giữ tham chiếu tới đối tượng đích và gọi trực tiếp, handler **không tự chạy**.

Ví dụ về các ranh giới:

```text
caller --> proxy(TaskService) --> handler --> target.execute()
                 |
                 +--> điểm quan sát qua proxy

caller ------------------------> target.execute()
                                      |
                                      +--> không qua handler của proxy

target.execute() --> this.internal()
                         |
                         +--> không phải một lời gọi mới qua proxy
```

Đây là giới hạn của **đường đi qua đối tượng trung gian**, không phải định nghĩa chung của AOP.

Một cơ chế weaving trực tiếp vào mã có thể quan sát các loại join point khác; mặt khác, chính cơ chế đó vẫn có thể bị giới hạn bởi các lớp được weaving, tình trạng nạp lớp, cấu hình và loại điểm mà nó định nghĩa.

## 6. Ví dụ Java 17: những thao tác proxy thực sự quan sát

Chương trình sau sử dụng Java Dynamic Proxy để **minh họa một tập điểm can thiệp giới hạn**. Nó không phải framework AOP và không tự triển khai các loại join point nâng cao.

Lưu file `JoinPointCoverageDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class JoinPointCoverageDemo {
    interface TaskService {
        void execute(String task);
        void ping();
    }

    static final class TaskServiceImpl implements TaskService {
        private int completed;

        TaskServiceImpl() {
            System.out.println("target.constructor");
        }

        @Override
        public void execute(String task) {
            System.out.println("target.execute " + task);
            internal();
            completed++;
        }

        @Override
        public void ping() {
            System.out.println("target.ping");
        }

        private void internal() {
            System.out.println("target.internal");
        }

        static void staticCheck() {
            System.out.println("target.staticCheck");
        }
    }

    public static void main(String[] args) {
        TaskServiceImpl target = new TaskServiceImpl();

        TaskService proxy = (TaskService) Proxy.newProxyInstance(
                TaskService.class.getClassLoader(),
                new Class<?>[] {TaskService.class},
                (proxyObject, method, values) -> {
                    System.out.println("intercept " + method.getName());
                    try {
                        return method.invoke(target, values);
                    } catch (InvocationTargetException e) {
                        throw e.getCause();
                    }
                }
        );

        System.out.println("-- proxy path --");
        proxy.execute("A");
        proxy.ping();

        System.out.println("-- direct path --");
        target.execute("B");
        TaskServiceImpl.staticCheck();

        System.out.println("completed " + target.completed);
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```bash
javac JoinPointCoverageDemo.java
java JoinPointCoverageDemo
```

**Stdout dự kiến chính xác:**

```text
target.constructor
-- proxy path --
intercept execute
target.execute A
target.internal
intercept ping
target.ping
-- direct path --
target.execute B
target.internal
target.staticCheck
completed 2
```

### 6.1. Phân tích từng hoạt động

| Hoạt động | Có dòng `intercept` của handler? | Lý do |
|---|---|---|
| `new TaskServiceImpl()` | Không | Java Dynamic Proxy được tạo **sau** khi target đã được xây dựng; nó không bọc constructor của target |
| `proxy.execute("A")` | **Có** | Lời gọi phương thức giao diện đi qua proxy |
| `proxy.ping()` | **Có** | Lời gọi phương thức giao diện đi qua proxy |
| `internal()` được gọi bên trong `execute()` | Không có intercept mới | Đường gọi nội bộ tới phương thức private trên target không đi qua proxy |
| `target.execute("B")` | Không | Caller dùng trực tiếp tham chiếu target |
| `TaskServiceImpl.staticCheck()` | Không | Lời gọi static không đi qua phương thức giao diện của proxy |

**Điều quan trọng:** việc không có dòng `intercept` cho một thao tác ở ví dụ **chỉ chứng minh giới hạn của cơ chế Java Dynamic Proxy đang triển khai**. Nó không chứng minh rằng mọi công cụ AOP đều không thể quan sát constructor, method private hoặc method static.

`completed` cuối cùng bằng `2` cho thấy cả `execute("A")` và `execute("B")` **đều chạy nghiệp vụ**, dù handler chỉ quan sát một đường gọi. Không được suy từ “advice không chạy” thành “thao tác nghiệp vụ không xảy ra”.

### 6.2. Vì sao ví dụ có `InvocationTargetException`?

Trong đoạn `method.invoke(target, values)`, nếu phương thức đích ném lỗi, lời gọi phản chiếu có thể bọc nguyên nhân trong `InvocationTargetException`. Handler tháo lớp bọc bằng `e.getCause()` để phần ngoài nhận lỗi gốc. Đây là đặc điểm của reflection trong **ví dụ minh họa**, không phải định nghĩa chung của advice.

Để xác nhận một cơ chế thực tế có bảo toàn ngoại lệ, return value và số lần gọi nghiệp vụ hay không, cần viết kiểm thử theo hợp đồng đó, nhất là khi có around advice.

## 7. Điều kiện pointcut không thể tự mở rộng tập loại join point

Giả sử mô hình AOP có tập loại join point được hỗ trợ:

```text
SupportedTypes = {method execution}
```

Ta tạo một pointcut rất rộng:

```text
P = chọn mọi phương thức phù hợp
```

**Dù P chọn mọi phương thức, nó không làm xuất hiện loại `field set` hay `constructor call` mới.** Biểu thức pointcut lựa chọn trên miền mà mô hình cung cấp, tương tự một bộ lọc chỉ chọn được các phần tử có trong tập đầu vào.

Cần tách hai kết luận:

- **“Không có join point loại đó”**: không thể lựa chọn bằng pointcut trong mô hình hiện có.
- **“Join point loại đó có, nhưng pointcut không chọn”**: có thể xem lại biểu thức, cấu hình điều kiện hoặc giá trị động.

Một cách chẩn đoán hợp lý là kiểm tra loại join point **trước**, rồi mới xét biểu thức lựa chọn.

## 8. Weaving scope: join point có hỗ trợ nhưng mã vẫn chưa được xử lý

Một công cụ AOP có hỗ trợ method execution ở mức mã không có nghĩa mọi lớp trong JVM đều đã được weaving.

Các nguyên nhân thực tế có thể bao gồm:

- Lớp thuộc mô-đun/thư viện nằm **ngoài phạm vi weaving** được cấu hình.
- Lớp được nạp trước khi cơ chế can thiệp phù hợp được kích hoạt; việc xử lý lại lớp có thể không được hỗ trợ.
- Môi trường runtime hoặc cách đóng gói không cho phép biến đổi một số lớp.
- Mô hình chỉ áp dụng đối với đối tượng được tạo và quản lý qua ranh giới định trước.
- Một đường thực thi đi thẳng đến đối tượng đích thay vì lớp trung gian.
- Điểm đang xét thuộc đoạn mã native hoặc ngoài tiến trình, vượt ra khỏi dạng biểu diễn mà cơ chế xử lý.

Các nguyên nhân này cần được xác minh **trên chương trình đang chạy**. Chỉ nhìn pointcut rồi nhận định “mọi lời gọi đều được chặn” là chưa đủ.

### 8.1. Join point tĩnh có trong chương trình nhưng không phát sinh khi chạy

Có những pointcut chọn một vị trí mã hợp lệ, nhưng nhánh chứa vị trí đó **không được thực thi** trong một ca thử cụ thể. Khi đó advice không chạy là điều đúng.

Ví dụ `if (false)` trong một đoạn giả định có thể khiến lời gọi không xảy ra; không nên kết luận do lỗi weaving. Phải tách **điểm được định nghĩa** khỏi **lần xuất hiện động của điểm**.

### 8.2. Không phải mọi lần “gọi cùng tên” đều là cùng loại điểm

Một lời gọi được tạo bằng reflection, method handle, generated code hoặc kỹ thuật runtime đặc biệt có thể đi qua đường thực thi khác lời gọi trực tiếp trong source. Một cơ chế weaving ở **constructor/method execution** có thể quan sát thân mã được weaving ngay cả khi caller dùng reflection; một cơ chế đặt tại **call site tĩnh** có thể có phạm vi khác. Không gán cùng kết luận cho hai cơ chế chỉ vì cả hai đều “làm AOP”.

## 9. Private, static, final: không có một quy tắc phủ định chung

Ba từ khóa Java `private`, `static`, `final` thường xuất hiện trong các câu “AOP không chặn được…” nhưng cần hiểu lý do kỹ thuật.

### 9.1. Private method

Phương thức private **không thể bị override từ lớp con** theo cơ chế đa hình thông thường. Vì vậy, một cơ chế chỉ chặn bằng cách override phương thức ở subclass sẽ có giới hạn với private method. Một cơ chế weaving trực tiếp ở điểm thực thi mã có thể có khả năng khác.

### 9.2. Static method

Static method gắn với lớp, không được dispatch đa hình theo tham chiếu instance như phương thức interface. Proxy của phương thức interface không thể tự đại diện cho mọi lời gọi static. Công cụ weaving ở call site hoặc method execution có thể xem xét một khả năng khác, tùy mô hình.

### 9.3. Final method và final class

Nếu một cách can thiệp yêu cầu tạo subclass và override một phương thức, thì **final method không thể override**, còn **final class không thể bị kế thừa**. Đây là hạn chế của cơ chế dựa trên subclass.

**Không kết luận rằng final method tuyệt đối không thể được quan sát.** Một proxy giao diện có thể chặn lời gọi ở lớp đại diện **trước khi chuyển tới phương thức triển khai** ngay cả khi triển khai có modifier final; một cơ chế weaving bytecode lại có ranh giới khác.

### 9.4. Self-invocation

Một phương thức được gọi bằng `this.otherMethod()` hoặc lời gọi ngầm `otherMethod()` từ bên trong đối tượng có thể bỏ qua proxy bên ngoài. Nhưng đây là kết quả của **đường gọi qua proxy**, không phải một đặc tính chung khẳng định AOP không quan sát lời gọi nội bộ.

Khi xem một hạn chế, hãy luôn hỏi: **“Nó là giới hạn của ngôn ngữ Java, của join point model hay chỉ của một chiến lược chặn?”**

## 10. Constructor, cấp phát và khởi tạo đối tượng

Yêu cầu “theo dõi mọi đối tượng mới” thường bị diễn giải quá rộng.

```java
Invoice invoice = new Invoice();
```

Đoạn này có thể liên quan đến:

- Biểu thức cấp phát/tạo thể hiện.
- Nơi gọi constructor (*constructor call*) theo mô hình AOP hỗ trợ loại điểm này.
- Việc thực thi một hoặc nhiều constructor trong chuỗi khởi tạo.
- Quá trình khởi tạo trường và trạng thái đối tượng.
- Trường hợp constructor ném ngoại lệ khiến biểu thức tạo không hoàn tất bình thường.

Một mô hình chỉ hỗ trợ method execution thông thường **chưa chắc** hỗ trợ constructor call hoặc constructor execution. Một cơ chế hỗ trợ constructor execution cũng **không tự trở thành máy đếm toàn bộ cấp phát trong JVM**.

Một số đường tạo đối tượng còn có thể khác `new` trực tiếp: factory trả đối tượng có sẵn, reflection, sao chép đối tượng hoặc các cơ chế tái tạo trạng thái. Phạm vi chặn theo constructor phải được diễn đạt bằng **loại join point được hỗ trợ** và **đường tạo cụ thể**.

### 10.1. Ví dụ về ranh giới không tương đương

Giả sử `OrderFactory.getOrCreate(id)` trả thể hiện đã lưu trong bộ nhớ đệm. Một lời gọi factory **không đồng nghĩa** một lần constructor chạy. Nếu muốn đo “bao nhiêu yêu cầu lấy đơn hàng”, chọn ranh giới factory có thể phù hợp hơn. Nếu muốn đo “bao nhiêu thể hiện mới được tạo”, cần quan sát ranh giới tạo thực sự.

Một pointcut tên `*create*` trên method chỉ là quy tắc dựa trên tên; nó không chứng minh phương thức đó thực sự tạo đối tượng.

## 11. Field access: khác biệt giữa thay đổi trạng thái và lời gọi method

Một chương trình có thể thay đổi trạng thái qua nhiều con đường:

```java
record.count++;
record.count = 10;
record.updateCount(10);
```

Đây là **mã minh họa rời**. Hai câu đầu truy cập trường trực tiếp (theo quy tắc truy cập hợp lệ trong ngữ cảnh); câu cuối là lời gọi method. Với một cơ chế AOP chỉ hỗ trợ method invocation qua proxy, **chỉ câu cuối** có thể đi qua điểm chặn của proxy nếu đối tượng được gọi qua proxy và phương thức thuộc giao diện được bọc.

Một mô hình hỗ trợ `get`/`set` join point có thể chọn các truy cập trường. Nhưng vẫn cần xét sự khác biệt giữa bytecode truy cập trường thông thường với những cơ chế phản chiếu hoặc truy cập bộ nhớ khác. Không suy từ việc hỗ trợ field set ở một đường đi rằng mọi thay đổi bộ nhớ đều được quan sát.

**Hệ quả thiết kế:** Nếu tính đúng đắn hoặc an toàn dựa vào việc chặn mọi thay đổi của một bất biến, chính sách nên đặt ở ranh giới sở hữu trạng thái và có kiểm thử chứng minh phạm vi, thay vì chỉ dựa vào pointcut trên một số setter.

## 12. Ngoại lệ: ném, lan truyền, bắt và xử lý là các mốc khác nhau

Ví dụ:

```java
try {
    service.perform();
} catch (IllegalStateException error) {
    recover(error);
}
```

Một cơ chế AOP có thể quan sát việc `perform()` thoát với ngoại lệ qua advice gắn vào method execution. Nhưng đó **không tự là** join point của câu `throw` gây ra ngoại lệ, cũng không tự là join point tại `catch`.

Cần tách:

1. **Nơi phát sinh ngoại lệ** (một lệnh `throw` hoặc runtime ném).
2. **Đường lan truyền** qua các phương thức.
3. **Nơi bắt/xử lý** ngoại lệ.
4. **Kết quả của một phương thức** (thoát bình thường hoặc ném lỗi).

Nếu cần quan sát “mọi exception handler”, phải xác minh mô hình có loại join point tương ứng. Nếu chỉ cần biết thao tác nghiệp vụ thất bại, việc quan sát ranh giới method với after-throwing advice (nếu được hỗ trợ) có thể là lựa chọn hợp lý hơn.

Một advice bắt lỗi cũng không bảo đảm xử lý được lỗi ở ngoài vùng áp dụng, chẳng hạn trước khi vào phương thức được quan sát hoặc trong một tiến trình khác.

## 13. Bất đồng bộ, callback và luồng thực thi

Giả sử một phương thức `startJob()` trả về ngay sau khi đưa tác vụ vào hàng đợi, còn công việc thực sự được chạy sau trên một luồng khác.

Nếu pointcut chọn **thực thi `startJob()`**, advice bao quanh phương thức đó thường chỉ quan sát thời gian từ lúc vào đến khi trả về hoặc ném lỗi. Nó **không mặc nhiên đo đến lúc tác vụ hoàn thành**.

Tương tự, những sự kiện có ý nghĩa ở luồng khác, callback, event loop hoặc quá trình xử lý ngoài tiến trình có thể là những thao tác **không thuộc loại join point** của điểm được chọn ban đầu.

Để quan sát một vòng đời bất đồng bộ, cần định nghĩa rõ:

- Mốc **bắt đầu lập lịch**.
- Mốc **bắt đầu thực thi công việc**.
- Mốc **hoàn tất/thất bại của công việc**.
- Cách liên kết ngữ cảnh, chẳng hạn mã tương quan qua các luồng/tiến trình.
- Những ranh giới có thể can thiệp bằng AOP và những ranh giới cần cơ chế quan sát khác.

Không được hiểu “đã chặn method trả về future” là “đã chặn sự kiện future hoàn tất”, trừ khi có cơ chế quan sát tương ứng.

## 14. Hoạt động ngoài tiến trình và giới hạn của join point nội bộ

Một lời gọi `sendMessage()` có thể được aspect quan sát, nhưng việc một hệ thống khác **nhận**, **xử lý** hoặc **ghi dữ liệu** là sự kiện ở ranh giới khác.

Ví dụ:

```text
Ứng dụng A:
  method sendMessage()       ← có thể là method join point ở A
         |
         v
      Mạng / broker
         |
         v
Ứng dụng B:
  xử lý thông điệp           ← không tự là join point của A
         |
         v
      Cơ sở dữ liệu
```

Advice trước/sau `sendMessage()` chỉ cho ta tín hiệu ở **vùng chương trình quan sát được**. Nó không chứng minh giao dịch đã được hệ thống B xử lý thành công. Muốn xác minh kết quả cuối, cần thiết kế event, acknowledgement, trace phân tán hoặc cơ chế quan sát thích hợp.

Điều này cũng đúng với hành vi do hệ điều hành, database trigger, tác vụ native hoặc tiến trình khác thực hiện: những sự kiện đó không tự nằm trong join point model của một công cụ AOP Java chỉ vì Java từng gọi một API liên quan.

## 15. Pointcut không chọn được loại điểm chưa được mô hình định nghĩa

Có hai tình huống rất khác nhau:

**Tình huống A:** Công cụ có method execution join point; pointcut chỉ chọn phương thức `saveOrder`, nên không chọn `cancelOrder`.

- Đây là **vấn đề điều kiện chọn**.
- Có thể sửa pointcut nếu nghiệp vụ yêu cầu thêm `cancelOrder`.

**Tình huống B:** Công cụ chỉ có method invocation qua proxy; yêu cầu mới là chặn phép gán `order.status = "DONE"` trực tiếp.

- Đây là **vấn đề loại điểm/ranh giới can thiệp**.
- Không thể khắc phục chỉ bằng cách dùng pointcut có wildcard rộng hơn.

Một nhóm thứ ba cũng cần phân biệt: công cụ **có** loại join point cần thiết, pointcut **đúng**, nhưng lớp hoặc đường thực thi **không được weaving/không đi qua ranh giới**. Lúc đó phải kiểm tra phạm vi triển khai và runtime path.

## 16. Những dấu hiệu dễ dẫn đến kết luận sai

### 16.1. “Advice không in log” không chứng minh pointcut sai

Có thể điểm cần theo dõi không xảy ra trong ca thử, log bị lọc, advice ném lỗi trước khi ghi, code chạy ngoài phạm vi weaving, hoặc ranh giới không được hỗ trợ. Cần kiểm tra từng tầng.

### 16.2. “Phương thức cùng tên” không chứng minh cùng join point

Overload, receiver, kiểu tham số, metadata, class loader và đường dispatch có thể khác nhau. Pointcut lựa chọn dựa trên điều kiện cụ thể, không dựa vào việc người đọc thấy hai tên giống nhau.

### 16.3. “Một thao tác đã được audit” không chứng minh mọi đường đi đều được audit

Một lời gọi qua proxy được ghi nhận, nhưng gọi trực tiếp có thể không. Cùng một nghiệp vụ có thể được kích hoạt từ API, batch, callback hoặc nội bộ mà đi qua các ranh giới khác nhau.

### 16.4. “Không thể chặn final/private/static” không phải kết luận chung

Phải nói rõ công cụ đang dùng là proxy giao diện, subclass proxy hay weaving mã; các loại điểm được hỗ trợ sẽ khác nhau. Không được suy luận vượt quá cơ chế.

### 16.5. “Có support” không đồng nghĩa “bật mặc định”

Một công cụ có thể hỗ trợ loại join point nào đó, nhưng cấu hình weaving, quyền biến đổi lớp, điều kiện phạm vi hoặc cách đóng gói hiện tại chưa kích hoạt nó. Hỗ trợ về lý thuyết cần được chứng minh bằng ca thử thực tế.

## 17. Quy trình chẩn đoán khi một thao tác không bị can thiệp

Có thể dùng quy trình sau để điều tra có hệ thống:

1. **Mô tả chính xác thao tác:** method call hay execution, constructor, field access, exception handler, object allocation, hoạt động bất đồng bộ hay sự kiện bên ngoài?
2. **Xác nhận mô hình join point:** đọc danh sách loại join point công cụ/cấu hình thực sự hỗ trợ; tránh suy từ tên AOP chung.
3. **Xác nhận điểm ứng viên:** vị trí mã/kiểu thành phần/call site nào đáng lẽ tạo join point?
4. **Kiểm tra pointcut:** biểu thức có chọn đúng chữ ký, kiểu, metadata và điều kiện động của sự kiện đó không?
5. **Kiểm tra weaving:** mã có nằm trong phạm vi được xử lý? Lớp có được nạp hay biến đổi đúng cách? Những đường gọi nào được áp dụng?
6. **Kiểm tra runtime path:** lời gọi có đi qua proxy/interceptor nếu cơ chế yêu cầu? Có self-invocation hay tham chiếu gốc không? Nhánh có thực sự được chạy?
7. **Kiểm tra hành vi advice:** có chạy nhưng log bị ẩn hoặc lỗi phát sinh? Có advice khác ảnh hưởng thứ tự/luồng điều khiển không?
8. **Đối chiếu ca dương và âm:** chuẩn bị ít nhất một sự kiện **phải khớp** và một sự kiện **không được khớp**; chứng minh hành vi nghiệp vụ vẫn đúng.
9. **Quyết định giải pháp:** sửa pointcut, mở rộng weaving, đổi ranh giới đặt chính sách hoặc chọn cơ chế quan sát thích hợp hơn.

Có thể ghi một bảng hỗ trợ ngắn như sau cho **cơ chế thực tế đã xác minh**, không nên ghi từ giả định:

| Thao tác yêu cầu | Mô hình hỗ trợ? | Pointcut chọn? | Weaving bao phủ? | Đã quan sát khi chạy? |
|---|---|---|---|---|
| Phương thức `submit()` qua ranh giới được quản lý | Cần xác minh | Cần kiểm tra | Cần kiểm tra | Cần kiểm thử |
| `this.submit()` bên trong target | Cần xác minh | Cần kiểm tra | Cần kiểm tra | Cần kiểm thử |
| `new Order()` | Cần xác minh | Cần kiểm tra | Cần kiểm tra | Cần kiểm thử |
| Ghi trường trực tiếp | Cần xác minh | Cần kiểm tra | Cần kiểm tra | Cần kiểm thử |
| Sự kiện được xử lý ở tiến trình khác | Không thuộc tự động join point nội bộ | Tùy ranh giới mới | Tùy công cụ khác | Cần observability liên tiến trình |

Bảng trên không coi “chưa chứng minh” là “không hỗ trợ”. Chỉ khẳng định âm khi có đặc tả, bằng chứng kỹ thuật hoặc ca kiểm thử đủ phạm vi.

## 18. Thiết kế giải pháp khi hành vi cần quan sát nằm ngoài mô hình

Có nhiều lựa chọn, tùy trách nhiệm và ranh giới hệ thống.

### 18.1. Dùng một ranh giới method rõ ràng

Nếu một thao tác trực tiếp trên trạng thái không có join point tương ứng, có thể **tổ chức lại thiết kế** sao cho thay đổi trạng thái đi qua một API có tên và hợp đồng rõ, như `order.markPaid()`. Khi đó, cơ chế AOP hỗ trợ method có thể áp dụng ở ranh giới được chọn.

Điều kiện là **mọi đường ghi hợp lệ** phải tuân thủ ranh giới đó. Nếu các nơi khác vẫn gán trường trực tiếp, không thể tuyên bố có bao phủ tuyệt đối.

### 18.2. Đặt chính sách tại factory hoặc decorator

Nếu cần kiểm soát việc tạo đối tượng mà công cụ không hỗ trợ constructor join point, một factory hoặc decorator có thể là ranh giới tập trung. Nó giúp tổ chức trách nhiệm rõ ràng, nhưng cũng chỉ bao phủ những nơi **chọn dùng** factory/decorator.

### 18.3. Chọn cơ chế weaving hỗ trợ đúng loại điểm

Khi cần field get/set, constructor call/execution, exception handler hoặc các sự kiện thấp hơn, có thể cần một công cụ AOP hoặc instrumentation có mô hình điểm can thiệp rộng hơn. Phải đánh giá chi phí, khả năng deploy, giới hạn runtime, tính bảo trì và quan hệ với công cụ debug.

Không giả định chuyển công cụ là đủ: vẫn phải xác minh điểm thực tế trong môi trường chạy.

### 18.4. Quan sát ở cấp có ngữ nghĩa phù hợp hơn

Một nhu cầu đo **mỗi message thực sự được xử lý**, **mỗi transaction commit**, hoặc **mỗi đối tượng runtime được cấp phát** đôi khi phù hợp hơn với tracing, hook của hạ tầng, event, agent runtime hoặc telemetry có chuyên môn phù hợp. AOP ở method có thể là một phần của giải pháp nhưng không thay thế mọi nguồn chứng cứ.

## 19. Những giới hạn quan trọng với an toàn và tính đúng đắn

### 19.1. Không đặt bảo đảm an toàn tuyệt đối trên vùng phủ chưa chứng minh

Nếu một chính sách kiểm soát quyền hoặc kiểm toán **bắt buộc** chỉ được gắn bằng một pointcut có khả năng bỏ sót đường gọi, hệ thống có thể tạo **khoảng trống chính sách**.

Nên tổ chức kiểm tra ở **ranh giới đáng tin cậy** và có kiểm thử âm/dương cho mọi entry point liên quan. AOP có thể giúp giảm lặp nhưng không thay thế thiết kế hợp đồng bảo mật và phân vùng trách nhiệm.

### 19.2. Thứ tự advice và thực thi nhiều lần

Một join point có thể phù hợp với nhiều aspect. Thứ tự bao ngoài/bao trong làm thay đổi đại lượng đo hoặc việc một advice có quan sát được ngoại lệ do advice khác phát sinh không. Với around advice, việc bỏ qua hoặc thực thi lại phần gốc có thể khiến số lần nghiệp vụ khác số lần join point mà người đọc mong đợi.

Phải kiểm tra **kết quả quan sát được** và **số lần thực hiện hành vi gốc**, không chỉ sự xuất hiện của một dòng log.

### 19.3. Điều kiện động và ngữ cảnh thực thi

Một pointcut có thể hỗ trợ điều kiện dựa trên đối số hoặc ngữ cảnh thread. Điều kiện sai ở một lần chạy không có nghĩa loại join point không được hỗ trợ. Trong xử lý bất đồng bộ, dữ liệu ngữ cảnh có thể không tự chuyển qua luồng; cần xác định đúng thời điểm và nguồn dữ liệu mà pointcut đánh giá.

### 19.4. Chi phí của việc cố bao phủ mọi thứ

Weaving rộng, ghi log mọi lần field access hoặc theo dõi từng thao tác tần suất cao có thể gây chi phí đáng kể và làm giảm khả năng đọc log. Xác định mục đích đo trước khi mở rộng loại điểm; không mặc định càng nhiều join point càng tốt.

## 20. Bài tập tự kiểm tra

**Bài 1 — Gán trường trực tiếp.** Một công cụ chỉ hỗ trợ method invocation qua proxy. Lập trình viên đặt pointcut “mọi method” nhưng vẫn không thấy log khi `object.flag = true`.

**Đáp án:** phép gán trường trực tiếp không phải lời gọi method qua proxy. Đó là **giới hạn mô hình/ranh giới**, không phải lỗi wildcard. Muốn chặn phải đổi điểm áp dụng hoặc cơ chế.

**Bài 2 — Hai cách gọi cùng nghiệp vụ.** `proxy.execute("A")` có advice; `target.execute("A")` không có. Có được kết luận pointcut về `execute` sai?

**Đáp án:** không. Cùng method nhưng đường gọi khác nhau; chỉ một đường đi qua proxy. Đây là **vấn đề đường thực thi**.

**Bài 3 — Constructor.** Có thể thêm pointcut tên “all new objects” vào cơ chế chỉ hỗ trợ method invocation và bảo đảm đếm mọi lần cấp phát đối tượng không?

**Đáp án:** không. Phải xác nhận có loại join point constructor/object allocation thích hợp; hơn nữa mọi cách tạo đối tượng chưa chắc đi qua một constructor-call join point duy nhất.

**Bài 4 — Lỗi được bắt.** Advice chạy khi `calculate()` thoát bằng ngoại lệ. Vậy mọi khối `catch` trong chương trình đều được can thiệp?

**Đáp án:** không. After-throwing advice ở method và join point của exception handler (nếu được hỗ trợ) là hai khái niệm khác nhau.

**Bài 5 — Công việc bất đồng bộ.** Advice quanh `enqueueJob()` ghi “completed” khi method trả về, nhưng tác vụ có thể còn chạy một giờ. Vấn đề ở đâu?

**Đáp án:** **sai ranh giới ngữ nghĩa**. Thời điểm method trả về chỉ phản ánh việc enqueue hoàn tất (theo hợp đồng của method), không phản ánh vòng đời job. Cần quan sát điểm hoàn tất job.

**Bài 6 — Final method.** Một người nói “AOP không can thiệp được vào phương thức final”. Bạn cần hỏi gì trước?

**Đáp án:** “Công cụ dùng subclass override, proxy giao diện, weaving vào mã hay cơ chế khác?” Giới hạn của subclass không phải quy tắc phổ quát cho tất cả mô hình AOP.

**Bài 7 — Lớp bên ngoài phạm vi weaving.** Công cụ hỗ trợ method execution, pointcut đúng chữ ký, nhưng lớp đích không được weaving. Thuộc tầng nào?

**Đáp án:** **weaving scope**. Cần kiểm tra vùng xử lý mã, thời điểm nạp lớp và cách công cụ áp dụng biến đổi, thay vì mở rộng pointcut một cách mù quáng.

## 21. Checklist trước khi tuyên bố một thao tác được AOP bao phủ

1. Tôi đã định nghĩa **chính xác loại hoạt động** cần quan sát chưa?
2. Loại đó có thuộc **join point model** của cơ chế đang dùng không?
3. **Pointcut** có chọn nó với đúng chữ ký và điều kiện động không?
4. **Weaving scope** có bao gồm mã/lớp liên quan không?
5. Mọi đường thực thi cần thiết có đi qua **ranh giới can thiệp** không?
6. Tôi đã phân biệt **lời gọi**, **thực thi**, **hoàn tất thành công** và **sự kiện nghiệp vụ cuối cùng** chưa?
7. Tôi có ca kiểm thử cho đường **phải được can thiệp** và đường **không được can thiệp** không?
8. Khi advice chạy, kết quả nghiệp vụ, ngoại lệ và số lần thực thi gốc có được giữ đúng hợp đồng không?
9. Nếu thao tác không có join point phù hợp, tôi đã chọn **ranh giới khác hoặc công cụ khác** thay vì chỉ sửa tên pointcut chưa?

## 22. Ghi nhớ

**Mô hình join point đặt ra miền sự kiện có thể lựa chọn. Pointcut chỉ lọc các điểm trong miền đó. Weaving quyết định phạm vi mã mà cơ chế thực sự xử lý, còn đường thực thi và điều kiện động quyết định sự kiện nào được quan sát lúc chạy.**

Một lời gọi method, một biểu thức `new`, một phép gán trường, một khối `catch`, một callback bất đồng bộ và một sự kiện ngoài tiến trình **không mặc nhiên là cùng loại điểm can thiệp**. Không thấy advice có thể là hành vi đúng, giới hạn mô hình, điều kiện không khớp, thiếu weaving hoặc đường gọi đi ngoài ranh giới.

Khi xử lý yêu cầu AOP, hãy xuất phát từ **thao tác thực sự cần quan sát** rồi xác minh khả năng của công cụ. Nếu loại hoạt động nằm ngoài join point model, thay đổi pointcut không tạo thêm loại điểm mới; cần điều chỉnh cách tổ chức ranh giới hoặc dùng cơ chế thích hợp.
