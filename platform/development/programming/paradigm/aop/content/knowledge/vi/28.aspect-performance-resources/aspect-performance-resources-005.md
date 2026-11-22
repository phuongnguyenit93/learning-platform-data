# Chi phí pointcut động và theo dõi luồng điều khiển trong AOP

## 1. Bài toán: pointcut đúng ngữ nghĩa nhưng tốn bao nhiêu tài nguyên?

Một **pointcut** xác định các **join point** mà advice có thể tác động. Tính đúng của pointcut là yêu cầu đầu tiên; kế tiếp phải hiểu cái giá mà chương trình trả để xác định liệu join point tại runtime có thỏa biểu thức hay không.

Xét hai ý định khác nhau:

- “Bắt mọi lần thực thi `save()` được khai báo trong `demo.persistence.Repository`”: kiểu, tên phương thức và chữ ký có thể được weaver xác định phần lớn ngay khi biên dịch/dệt.
- “Bắt `save()` **chỉ trong khi** `checkout()` đang nằm trên chuỗi gọi hiện hành”: ngoài điều kiện chữ ký còn cần **kiểm tra trạng thái động** của luồng điều khiển.

Với ý định thứ hai, không đủ để xét mã `save()` nằm trong file nào. `save()` có thể được gọi sâu qua các helper; một lần chạy `save()` thuộc checkout, lần khác thì không. Muốn chọn đúng, hệ thống AOP phải phân biệt **hai lần thực thi của cùng một phương thức** bằng ngữ cảnh lúc chạy.

Bài học dùng biểu thức **AspectJ** để giải thích AOP cơ bản và nâng cao. Các triển khai AOP khác nhau hỗ trợ các loại join point, ngữ nghĩa và kỹ thuật weaving khác nhau; các nhận xét hiệu năng dưới đây vì vậy là **nguyên tắc phân tích**, không phải cam kết về một con số hay một cách triển khai duy nhất.

Sau bài học, bạn có thể phân biệt điều kiện tĩnh và động, giải thích `cflow`/`cflowbelow`, xác định ba nguồn chi phí chính, chọn mẫu pointcut chặt chẽ hơn mà không làm sai chức năng, và đo overhead có kiểm soát.

## 2. Shadow lúc weaving và join point lúc thực thi

Trong AOP có weaving, cần tách hai lớp:

1. **Join point shadow:** vị trí mã/bytecode có khả năng tạo ra một join point phù hợp. Weaver phân tích loại sự kiện, chữ ký, vị trí mã, modifier và metadata để chọn hoặc loại các shadow.
2. **Join point runtime:** một lần thực thi cụ thể tại shadow đó. Một vị trí `execute()` có thể được chạy hàng triệu lần và mỗi lần có đối tượng, đối số hoặc call flow khác nhau.

Một pointcut chỉ dùng các thuộc tính đã rõ ở lúc weaving thường có thể được xác định trước cho từng shadow. Nếu điều kiện phụ thuộc trạng thái runtime, weaver có thể chèn phép kiểm tra để quyết định **ở từng lần chạy**. Việc chèn và tối ưu khác nhau theo compiler/weaver.

Ví dụ AspectJ:

```aspectj
execution(void demo.Store.save(..))
```

Ý nghĩa: chọn execution join point của phương thức có kiểu trả về, kiểu khai báo, tên và tham số phù hợp. Một phần lớn matching được giải quyết bằng chữ ký thực tế của mã.

```aspectj
execution(void demo.Store.save(..))
    && cflow(execution(void demo.Checkout.run()))
```

Ý nghĩa: chỉ chọn những lần thực thi `save(..)` diễn ra khi một `run()` phù hợp đang còn hoạt động trong call flow. Phần `execution(...)` giới hạn shadow; phần `cflow(...)` cần thông tin về thời điểm chạy.

**Lưu ý:** “Static matching không cần dynamic test” **không đồng nghĩa “advice miễn phí”**. Một khi advice thực sự chạy, việc gọi advice, đo thời gian, tạo log, đọc thông tin join point, cấp phát object hay đồng bộ vẫn có overhead.

## 3. Các thành phần pointcut theo khả năng xác định trước

| Pointcut designator (AspectJ) | Điều kiện chọn | Nguồn chi phí cần cân nhắc |
| --- | --- | --- |
| `execution(...)`, `call(...)` | Loại join point và mẫu chữ ký | Có thể lọc shadow sớm; các shadow được advice vẫn làm phát sinh code được dệt. |
| `within(TypePattern)` | Mã chứa join point được định nghĩa trong type phù hợp | Dựa vào phạm vi từ vựng, thường lọc sớm. |
| `withincode(MethodPattern)` | Join point thuộc đoạn mã được định nghĩa bên trong method/constructor phù hợp | Dựa vào vị trí mã, thường lọc sớm. |
| `this(T)`, `target(T)` | Đối tượng hiện tại hoặc đối tượng đích | Có thể cần kiểm tra kiểu runtime; bản chất khác `within`. |
| `args(T, ..)` | Kiểu/ngữ cảnh đối số phù hợp | Có thể cần kiểm tra đối số hoặc binding runtime; khác mẫu tham số khai báo trong `execution`. |
| `if(booleanExpression)` | Một điều kiện tính lúc chạy | Có thể rẻ hoặc rất đắt tùy expression được gọi. |
| `cflow(P)` | Trong flow bắt đầu bởi join point P, **kể cả P** | Cần duy trì và tra cứu trạng thái call flow. |
| `cflowbelow(P)` | Trong flow bắt đầu bởi P nhưng **loại chính P** | Cũng cần tracking flow, khác về ngữ nghĩa. |

Không có thứ tự “nhanh nhất đến chậm nhất” áp dụng cho mọi trường hợp. JVM có thể tối ưu kiểm tra kiểu; `if` có thể chỉ đọc cờ hoặc thực hiện I/O; `cflow` có thể dùng cách theo dõi khác nhau khi có hoặc không binding. Hiệu năng thực tế phụ thuộc số lần vào/ra flow, tần suất chạy shadow, số lần advice match, JVM/JIT, bộ nhớ và contention.

### Những phép lọc nhìn giống nhau nhưng không tương đương

```aspectj
within(demo.Checkout)
this(demo.Checkout)
```

`within` nói về **nơi đoạn mã định nghĩa**, còn `this` nói về **đối tượng trong ngữ cảnh join point**. Ví dụ một `call` nằm trong lớp khác nhưng gọi đến đối tượng Checkout có thể tạo kết quả khác.

```aspectj
withincode(void demo.Checkout.run())
cflow(execution(void demo.Checkout.run()))
```

`withincode` nói về vị trí mã viết **trực tiếp bên trong thân `run()`**; `cflow` nói về các sự kiện **diễn ra trong khoảng thời gian `run()` đang hoạt động**. Dùng cái rẻ hơn mà không kiểm tra yêu cầu có thể làm mất join point hợp lệ.

## 4. `cflow` và `cflowbelow` hoạt động ra sao?

Giả sử lời gọi đồng bộ:

```text
main()
└── checkout()        ← P = execution(checkout())
    └── validate()
        └── lookup()
            └── normalize()
```

Với `P = execution(void demo.Shop.checkout())`:

- `cflow(P)` chọn P và những join point thuộc call flow của P trong thời gian P còn đang thực thi.
- `cflowbelow(P)` chỉ chọn join point **bên dưới** P, bỏ chính P.
- Khi `checkout()` kết thúc, kể cả kết thúc bất thường bằng exception, vùng flow liên quan phải kết thúc; một `lookup()` gọi độc lập sau đó không còn thuộc flow.
- Khi P lồng nhau do đệ quy, một join point có thể nằm bên dưới P ở outer frame dù bản thân cũng là một P ở inner frame. Vì thế không thể suy rằng `cflowbelow(P)` luôn loại mọi lần chạy phương thức P trong trường hợp đệ quy.

Điểm chính: cùng một execution shadow của `lookup()` có thể thỏa `cflow(P)` trong lần gọi thứ nhất, không thỏa ở lần gọi thứ hai. Thông tin “đang ở trong flow?” không thể xác định chỉ từ chữ ký của `lookup()`.

### Theo dõi flow đòi hỏi duy trì thông tin gì?

Về mặt khái niệm, weaver có thể phải:

1. Đánh dấu **vào** một join point gốc P, hỗ trợ nhiều mức lồng nhau thay vì một boolean toàn cục.
2. Đánh dấu **thoát** P qua đường return bình thường lẫn exception, tránh để lại trạng thái sai.
3. Tại các shadow ứng viên còn lại, **kiểm tra** trạng thái P có đang hoạt động hay không.
4. Nếu pointcut bind `this`/`target`/`args` từ flow gốc, lưu và cung cấp dữ liệu ngữ cảnh tương ứng cho advice.

Một triển khai có thể dùng counter hoặc stack gắn với ngữ cảnh thực thi, đôi khi gần với chi phí `ThreadLocal`; cấu trúc cụ thể phụ thuộc implementation và việc có binding. Khi chỉ cần biết P có hoạt động hay không, tracking có thể đơn giản hơn trường hợp cần đọc tham số từ frame P.

Có **hai nơi tốn chi phí**: vùng P lúc vào/ra, và shadow đích Q lúc hỏi “hiện có P không?”. Nếu Q được gọi cực thường xuyên nhưng advice hầu như không match, phép hỏi trạng thái âm tính vẫn có thể tạo overhead.

## 5. Ví dụ AspectJ tự chạy: `lookup()` trong và ngoài `checkout()`

Ví dụ sử dụng AspectJ native source weaving, không yêu cầu framework. Cần JDK 17+, AspectJ compiler `ajc` hỗ trợ Java 17 và thư viện `aspectjrt.jar` tương ứng.

Tạo hai tệp:

```text
demo/
  Shop.java
  FlowTrace.aj
```

**Tệp `demo/Shop.java`**

```java
package demo;

public class Shop {
    public static void main(String[] args) {
        Shop shop = new Shop();
        shop.checkout();
        shop.lookup();
        shop.checkout();
    }

    void checkout() {
        validate();
    }

    void validate() {
        lookup();
    }

    void lookup() {
        System.out.println("lookup");
    }
}
```

**Tệp `demo/FlowTrace.aj`**

```java
package demo;

public aspect FlowTrace {
    pointcut insideCheckout():
        cflow(execution(void demo.Shop.checkout()));

    before(): execution(void demo.Shop.lookup())
              && insideCheckout() {
        System.out.println("[flow] lookup inside checkout");
    }
}
```

Giả sử `ASPECTJ_HOME` chỉ đến thư mục cài AspectJ, `ajc` đã có trong `PATH` và shell có cú pháp biến môi trường tương thích Unix:

```bash
ajc -17 -classpath "$ASPECTJ_HOME/lib/aspectjrt.jar" -d out demo/Shop.java demo/FlowTrace.aj
java -cp "out:$ASPECTJ_HOME/lib/aspectjrt.jar" demo.Shop
```

Trên Windows, thay dấu phân cách classpath `:` bằng `;` và dùng biến môi trường phù hợp với shell. `javac` đơn thuần không biên dịch trực tiếp cú pháp `aspect`/`before` trong file `.aj`.

**Stdout của chương trình khi weaving thành công:**

```text
[flow] lookup inside checkout
lookup
lookup
[flow] lookup inside checkout
lookup
```

Giải thích chính xác:

1. Lần `checkout()` đầu tiên gọi `validate()` rồi `lookup()`: advice chạy trước thân `lookup()`, sau đó in `lookup`.
2. Lần gọi `shop.lookup()` trực tiếp từ `main()`: ngoài checkout flow nên **không có** dòng `[flow] ...`.
3. Lần `checkout()` thứ hai có kết quả giống lần đầu.

Giữ nguyên `Shop.java` rồi thử pointcut khác để học phân biệt ngữ nghĩa:

| Biểu thức advice | Số lần chạy advice trong ví dụ | Lý do |
| --- | ---: | --- |
| `execution(void demo.Shop.lookup())` | 3 | Mọi lần execution lookup. |
| `execution(void demo.Shop.lookup()) && cflow(execution(void demo.Shop.checkout()))` | 2 | Chỉ hai lần trong flow checkout. |
| `execution(void demo.Shop.lookup()) && cflowbelow(execution(void demo.Shop.checkout()))` | 2 | lookup ở dưới checkout; khác biệt loại root P không tác động case này. |
| `execution(void demo.Shop.lookup()) && withincode(void demo.Shop.checkout())` | 0 | Thân lookup được định nghĩa trong lookup, không nằm trong source body checkout. |
| `call(void demo.Shop.lookup()) && withincode(void demo.Shop.validate())` | 2 | Hai call site được thực thi trong thân validate. |

Bảng chỉ áp dụng cho code, các method và phạm vi weaving ở trên. Với lời gọi đi qua helper khác, `call && withincode` có thể mất sự kiện còn `execution && cflow` vẫn đúng.

**Tách việc kiểm tra:** có thể thêm `-showWeaveInfo` vào `ajc` để xem thông tin dệt. Thông báo của compiler không phải stdout của `java demo.Shop` và có thể đổi theo phiên bản.

## 6. Tổng chi phí của pointcut động

Một mô hình **định hướng** để phân rã overhead:

```text
Tổng overhead ≈ chi phí vào/ra vùng flow P
               + Σ (số lần đến shadow Q × chi phí kiểm tra động)
               + Σ (số lần advice match × chi phí body advice)
               + tác động gián tiếp đến JIT, bộ nhớ, GC và lịch chạy
```

Đây không phải công thức dự đoán thời gian chính xác. Nó giúp đặt phép đo vào đúng nhóm:

- **Root P frequency:** checkout được gọi thường xuyên sẽ làm số lần vào/ra vùng theo dõi tăng, kể cả khi không có `save()`.
- **Candidate shadow frequency:** `save()` bị gọi rất nhiều lần khiến mọi dynamic test gắn với shadow đó quan trọng, dù flow chỉ đúng trong một phần nhỏ.
- **Matched advice frequency:** body advice có thể tạo chuỗi, log, truy cập clock, đồng bộ hóa hoặc I/O ở mỗi lần match.
- **Binding và allocation:** truy xuất `thisJoinPoint`, args, stack và correlation data có thể phát sinh object hoặc ảnh hưởng JIT, tùy cách compiler tối ưu.
- **Concurrency:** nhiều thread có trạng thái flow riêng, cache/GC và logging contention ảnh hưởng tổng throughput và tail latency.

Ví dụ giả định một method Q chạy 1.000.000 lần, chỉ 10.000 lần thuộc checkout flow. Với `execution(Q) && cflow(P)`, advice chạy tại các lần phù hợp, nhưng điều kiện flow có thể vẫn cần được kiểm tra ở nhiều lần Q còn lại. Với chỉ `cflow(P)` làm pointcut advice, tập shadow ứng viên rộng hơn nhiều. Đây là ví dụ về **tần suất**, hoàn toàn không ngầm khẳng định số nanosecond hay số lệnh máy của bất cứ phiên bản AspectJ nào.

## 7. Vì sao pointcut quá rộng đắt đỏ?

Xem biểu thức:

```aspectj
before(): cflow(execution(* demo..*.checkout(..))) {
    // Thu thập metric tại mọi join point mà pointcut chọn.
}
```

Trong một flow đang hoạt động, nó có thể match rất nhiều loại join point được weaver hỗ trợ; vì thế advice có khả năng chạy tại rất nhiều vị trí, và nhiều candidate phải hỏi trạng thái runtime. Nếu yêu cầu thực tế chỉ là “chỉ ghi metric khi Repository.save() diễn ra bên trong checkout”, nên diễn đạt đúng đối tượng:

```aspectj
before(): execution(* demo.persistence.Repository.save(..))
          && cflow(execution(* demo..*.checkout(..))) {
    // Metric tại execution save(...) trong checkout flow.
}
```

Phần chữ ký `execution(* demo.persistence.Repository.save(..))` giúp loại các shadow không liên quan trước khi nghĩ đến flow. Chỉ còn những lần tới shadow phù hợp mới cần xử lý phần động theo cách weaver thực sự sinh mã.

Không nên tối ưu bằng cách biến `execution` thành `call` tùy tiện: một bên quan sát *thực thi thân method*, bên kia quan sát *call site*; phạm vi dệt và số lần quan sát có thể khác.

### Biểu thức `if(...)` cần cảnh giác đặc biệt

```aspectj
pointcut enabled():
    if(demo.Flags.isEnabled());

before(): execution(* demo.Worker.perform(..)) && enabled() {
    // Demo: chỉ match khi điều kiện động trả true.
}
```

Đây là ví dụ hình thức, không phải chương trình độc lập; `demo.Flags`/`demo.Worker` phải được định nghĩa mới biên dịch được. Nếu `isEnabled()` chỉ đọc boolean thì có thể nhẹ; nếu nó truy vấn ổ đĩa, gọi mạng, khóa hay tạo đối tượng thì việc kiểm tra trên đường nóng có thể rất đắt.

Đặc biệt, **đừng đặt tác dụng phụ trong `if()` dựa vào giả định thứ tự đánh giá của `&&`/`||`**. Weaver AspectJ có thể chuyển đổi biểu thức pointcut thành DNF và sắp xếp lại thành phần để matching hiệu quả; thứ tự viết từ trái sang phải không phải hợp đồng thứ tự gọi các điều kiện.

## 8. Lựa chọn static scope khi đúng ý định

Có hai dạng yêu cầu khác nhau:

**A. “Lời gọi `save()` được viết trong thân `checkout()`.”**

```aspectj
call(void demo.persistence.Repository.save(..))
    && withincode(void demo.Checkout.checkout())
```

Đây là ràng buộc **vị trí code**, phù hợp khi muốn quan sát call site trực tiếp trong checkout. Nó không tự bao gồm `save()` được gọi từ helper khác.

**B. “`save()` thực thi bất cứ lúc nào checkout còn nằm trên call flow.”**

```aspectj
execution(void demo.persistence.Repository.save(..))
    && cflow(execution(void demo.Checkout.checkout()))
```

Đây là ràng buộc **động**, bao gồm trường hợp checkout → helper → save. A và B không tương đương, vì vậy chỉ thay khi đã xem lại tiêu chí chức năng.

Tương tự, `within(demo.checkout..*)` chỉ phản ánh nơi mã được định nghĩa; nó không chứng minh có một `checkout()` đang hoạt động.

AspectJ thường chủ động tối ưu thứ tự matching, do đó không cần cố xếp thành phần `&&` theo “rẻ ở bên trái” mà bỏ qua tính chính xác. Cách hữu ích hơn là làm pointcut rõ **kind**, **scope** và **context**, giúp tập shadow ứng viên chặt hơn.

## 9. Chi phí lưu và binding ngữ cảnh trong flow

Trong ví dụ `insideCheckout()`, ta chỉ cần biết một checkout có đang hoạt động hay không. Một trường hợp nâng cao cần lấy dữ liệu của join point đã kích hoạt flow để sử dụng ở join point nằm sâu phía dưới:

```aspectj
pointcut requestFlow(String requestId):
    cflow(execution(void demo.Gateway.accept(String))
          && args(requestId));

before(String requestId):
    execution(void demo.Worker.execute())
    && requestFlow(requestId) {
    System.out.println("request=" + requestId);
}
```

Đây là đoạn minh họa cần lớp `Gateway` và `Worker` để biên dịch. Nó cho thấy khi flow gốc `accept(String)` nhận `requestId`, pointcut có thể truyền binding đó đến advice chạy trong flow. Để làm vậy, triển khai có thể cần giữ nhiều thông tin hơn so với việc chỉ theo dõi một cờ “trong flow”.

Nếu không cần giá trị từ P, đừng bind thêm đối tượng/đối số chỉ để hiển thị cho thuận tiện. Nếu cần tên method tĩnh, `thisJoinPointStaticPart` thường thích hợp hơn thao tác với `thisJoinPoint` động. Khi thật sự cần args/this/target ở runtime, phải chọn API đúng ngữ nghĩa và đánh giá chi phí riêng.

Số object giữ lại, tần suất truy xuất, cách cleanup khi flow kết thúc, độ sâu đệ quy và số lượng thread là những chỉ số đáng đo. Không thể suy từ cú pháp rằng mọi `cflow` luôn sử dụng một stack cấp phát object trong mọi phiên bản.

## 10. Đệ quy, exception, nhiều thread và async

### Đệ quy

Khi P gọi lại P, có nhiều mức P còn đang hoạt động. Một boolean `static isInCheckout` do ứng dụng tự quản lý không thể biểu diễn đúng mọi trường hợp: nếu P bên trong thoát, P bên ngoài vẫn còn active. Theo dõi flow đúng phải duy trì nesting/depth tương ứng.

Đệ quy cũng làm câu “`cflowbelow(P)` không bao giờ match P” trở nên sai nếu không có ngữ cảnh: join point P nội bộ có thể nằm bên dưới P ngoài. Phải kiểm tra biểu thức thực tế và call tree.

### Exception

Flow P có thể kết thúc qua return hoặc exception. Cơ chế tracking đúng phải cleanup khi frame P thực sự thoát. Nếu ứng dụng tự duy trì context, hãy dùng cấu trúc `try/finally` thích hợp thay vì chỉ xóa cờ ở đường return bình thường.

### Nhiều thread

Không được dùng một cờ global để biểu diễn “đang ở trong checkout” của toàn tiến trình khi các request chạy song song. Theo dõi call flow phải bám vào ngữ cảnh thực thi có ý nghĩa. Trong AspectJ, `cflow` thường được mô tả có chi phí gần với việc dùng trạng thái kiểu `ThreadLocal`, nhưng chi tiết thay đổi theo phiên bản và tình huống có binding.

### Ranh giới asynchronous

```text
Thread A: checkout() ── submit(task) ── return
                         |
                         v
Thread B:              task.run() ── lookup()
```

Task được gửi từ trong checkout **không bảo đảm** `lookup()` ở thread khác được coi nằm trong dynamic call flow của checkout. Quan hệ nghiệp vụ “thuộc cùng request” khác với chuỗi điều khiển Java hiện còn active. Khi cần correlation ID xuyên executor, queue hay thread boundary, phải thiết kế capture/propagate/restore context tường minh và cleanup để tránh rò rỉ dữ liệu giữa các task.

| Tình huống | Điểm cần kiểm tra |
| --- | --- |
| checkout → validate → lookup trên cùng call stack | `cflow` biểu thị quan hệ động mong muốn nếu join point được dệt. |
| checkout đệ quy rồi gọi lookup | Có flow lồng nhau; kiểm tra `cflowbelow` cẩn thận. |
| checkout ném exception | Trạng thái flow phải được kết thúc đúng. |
| Nhiều checkout trên các thread khác nhau | Không dùng flag toàn cục; đo chi phí trên tải đồng thời thực. |
| Task chạy sau khi checkout đã return ở thread khác | Không tự giả định `cflow` truyền context; cần propagation riêng khi yêu cầu. |

## 11. Cách đo overhead đúng bằng benchmark

Không sử dụng một lần đo `System.nanoTime()` trong một chương trình vừa khởi động để khẳng định pointcut này chậm hơn pointcut kia. JIT warmup, class loading, GC, scheduler, frequency scaling và logging có thể làm kết quả sai lệch.

### Thiết kế các phiên bản đối chứng

Dùng cùng logic nghiệp vụ, đầu vào và số lượng lời gọi, rồi so:

| Cấu hình | Câu hỏi cần trả lời |
| --- | --- |
| A. Không có aspect | Baseline của nghiệp vụ. |
| B. Aspect với chữ ký tĩnh và advice rỗng/tối giản | Chi phí weaving và đi qua advice match. |
| C. Giống B nhưng thêm điều kiện runtime như `target` hoặc `args` | Tác động riêng của kiểm tra đối tượng/đối số. |
| D. Giống B nhưng thêm `cflow(P)`, giữ advice tối giản | Chi phí tracking flow và dynamic test. |
| E. Chỉ dùng `cflow(P)` với phạm vi rất rộng | Tác động của việc có nhiều candidate join points. |
| F. Cùng yêu cầu như E nhưng ràng buộc `execution(Q) && cflow(P)` | Tác động của việc giới hạn shadow bằng mẫu tĩnh. |
| G. Giống F, bổ sung log/capture context trong advice | Chi phí do body advice và allocation. |

Không đánh đồng “fewer matches” với “faster implementation of the same behavior”: B và D có số advice match khác nhau nếu Q không luôn nằm trong flow. Để cô lập thuần chi phí `cflow`, cần xây workload sao cho tập match mong muốn bằng nhau, hoặc ghi nhận và giải thích sự khác biệt.

### Các bước đo đề xuất

1. **Test chức năng trước:** kiểm chứng số lần advice mong đợi với trường hợp có/không có checkout, helper gián tiếp, đệ quy, exception và async.
2. **Cố định build:** ghi JDK, AspectJ compiler/weaver, JVM options, hardware, classpath, tập class được dệt và cấu hình chạy.
3. **Dùng JMH** khi đo microbenchmark Java: warmup, nhiều iteration/fork, tránh dead-code elimination, dùng kết quả được tiêu thụ đúng cách như `Blackhole`.
4. **Tách logging khỏi phép đo matching:** đừng gọi `System.out.println` tại hàng triệu join points trong benchmark muốn đo nanosecond.
5. **Thay đổi tỷ lệ match:** nếu chỉ 1% Q ở trong P, chi phí động bị chi phối bởi candidate check khác trường hợp 90% match.
6. **Thay đổi root frequency và depth:** cùng số lượng Q nhưng tăng số lần vào/ra P hoặc đệ quy có thể ảnh hưởng chi phí tracking.
7. **Đo đa chiều:** throughput, latency/p95/p99, CPU, allocation/op, GC, concurrency, số lần advice thực sự chạy.
8. **Profile JVM:** dùng Java Flight Recorder hoặc profiler phù hợp để xem có thực sự tốn ở dynamic tests, body advice, classloading, locks hay logger.
9. **Lặp lại trên workload thật:** microbenchmark có thể không phản ánh tương tác I/O, cache, JIT hay điều phối executor trong sản phẩm.

Báo cáo kết quả nên có đơn vị, thiết lập benchmark, số lần đo, độ biến thiên và kiểm tra đúng chức năng. Không gán một hệ số “`cflow` chậm hơn x lần” nếu không có thực nghiệm trên môi trường cụ thể.

## 12. Khắc phục overhead theo dấu hiệu

| Dấu hiệu quan sát | Giả thuyết hợp lý | Phép kiểm chứng / hướng sửa |
| --- | --- | --- |
| CPU tăng ở method rất nóng | Nhiều dynamic test hoặc advice chạy quá thường | Profile Q, thu hẹp chữ ký/kiểu join point, đo event count. |
| Advice rất hiếm nhưng vẫn có overhead | Flow P được tracking hoặc Q kiểm tra âm tính nhiều lần | Đếm root entries, candidate visits và matched visits riêng. |
| GC tăng sau weaving | Truy xuất join point context, bind args, tạo string/log | Giảm metadata động không cần thiết và allocation trong advice. |
| P được gọi liên tục, không có Q | Chi phí vào/ra P có thể chiếm tỷ lệ lớn | So A/D với cùng Q nhưng tần suất P thay đổi. |
| Thread pool chạy sai ngữ cảnh | `cflow` không biểu thị correlation async mong muốn | Thiết kế propagation theo task, teardown chuẩn. |
| Thay `cflow` bằng `withincode` rồi metric giảm mạnh | Có thể đã bỏ mất lời gọi gián tiếp, khác ngữ nghĩa | Test checkout → helper → Q và call-site thực tế. |
| Benchmark chủ yếu thấy stdout/logger | Advice I/O lấn át pointcut matching | Dùng advice tối giản, đo logging riêng. |

Để tránh sửa mò, dùng `ajc -showWeaveInfo` khi khả dụng để kiểm tra join points nào đã được dệt, sau đó kiểm tra chính số lần vào P và số Q đã xét. Compiler diagnostic và profiling là hai nguồn chứng cứ khác nhau: được dệt không chứng minh runtime đang hot, và advice không xuất hiện log không chứng minh rằng chẳng có dynamic test nào được thực hiện.

## 13. Sai lầm thường gặp

**1. “Cứ dùng `cflowbelow` cho nhanh hơn `cflow`.”** Hai điểm này khác tập sự kiện được chọn; không có cam kết rằng một điểm luôn rẻ hơn. Chọn dựa trên việc P có cần được match hay không và trường hợp nested P.

**2. “Mọi pointcut tĩnh đều miễn phí.”** Static matching có thể không cần kiểm tra điều kiện runtime, nhưng advice khi chạy và thay đổi bytecode có thể tác động CPU, code size/JIT.

**3. “Chỉ khi advice được gọi mới có overhead.”** Chưa chắc: việc duy trì root P và kiểm tra điều kiện âm tính tại Q có thể tạo overhead.

**4. “Cứ đặt điều kiện rẻ bên trái `&&`.”** Weaver AspectJ có thể chuẩn hóa và sắp xếp lại các thành phần; không dựa vào thứ tự source để suy short-circuit hay đặt tác dụng phụ vào `if()`.

**5. “Thay `cflow` bằng `within` hoặc `withincode` sẽ giữ nguyên nghĩa.”** Lexical location và dynamic call flow là hai quan hệ khác nhau; nếu có helper, lời gọi gián tiếp sẽ lộ rõ sự khác biệt.

**6. “Theo dõi một biến `static boolean` là đủ.”** Sai trong đệ quy, exception hoặc nhiều thread; việc cleanup sai còn có thể gây rò rỉ trạng thái từ request này sang request khác.

**7. “Thread sinh ra từ checkout đương nhiên tiếp tục `cflow`.”** Không tự giả định context xuyên ranh giới async; phải quan sát và truyền dữ liệu logic một cách tường minh nếu bài toán yêu cầu.

**8. “Một lần đo thời gian trên laptop cho hệ số overhead ổn định.”** Kết quả phụ thuộc compiler/weaver, JVM, tần suất, root nesting, advice body, logging, allocation và concurrency.

## 14. Bài luyện tập có đáp án

Giả sử `checkout()` gọi `helper()`, rồi `helper()` gọi `save()`; ngoài ra `main()` gọi `save()` trực tiếp một lần.

**Câu 1:** pointcut nào phù hợp để bắt *execution của save khi checkout đang hoạt động*, kể cả đi qua helper?

```aspectj
execution(void demo.Repository.save())
    && cflow(execution(void demo.Checkout.checkout()))
```

**Đáp án:** biểu thức trên. Dùng `withincode(void demo.Checkout.checkout())` với `execution(save)` không tương đương, bởi thân `save` được định nghĩa ở Repository.

**Câu 2:** nếu checkout gọi `save` thông qua helper được khai báo bên ngoài Checkout, có thể chỉ dùng `call(save) && withincode(checkout)` không?

**Đáp án:** không, vì call site của `save` nằm trong `helper`. Muốn chọn theo call flow cần một điều kiện động phù hợp; nếu yêu cầu chỉ bắt lời gọi trực tiếp viết trong checkout thì mới dùng lexical condition.

**Câu 3:** lời gọi `save` chạy 100.000 lần, chỉ 100 lần thuộc checkout. Điểm nào cần đo ngoài số lần advice match?

**Đáp án:** số lần root P bắt đầu/kết thúc, số Q shadow visits/các runtime checks có thể được thực thi, chi phí body advice, allocation và JIT. Không kết luận 100 advice tức chỉ có 100 phép kiểm tra.

**Câu 4:** sau khi chuyển từ `cflow` sang `withincode`, số event giảm từ 100 xuống 10 và ns/op giảm đáng kể. Có thể kết luận tối ưu thành công chưa?

**Đáp án:** chưa; hai biểu thức có thể đã chọn tập join point khác nhau. Phải xác nhận mục tiêu chức năng thực sự chỉ cần 10 event kia trước khi so hiệu năng.

**Câu 5:** nếu `checkout()` gửi task sang thread pool rồi return, `cflow` có thay thế được việc truyền `requestId` vào task không?

**Đáp án:** không nên. Cần một cơ chế truyền ngữ cảnh độc lập qua boundary async nếu muốn giữ quan hệ request logic, bao gồm cleanup đúng để tránh dữ liệu rò rỉ khi thread được tái sử dụng.

## 15. Checklist trước khi áp dụng

- [ ] Đã xác định đúng kind: `call`, `execution` hay join point khác.
- [ ] Đã giới hạn shadow bằng type/signature/lexical scope khi đúng ngữ nghĩa.
- [ ] Đã phân biệt kiểm tra động `this/target/args/if` với bộ lọc dựa trên chữ ký.
- [ ] Đã hiểu `cflow` bao gồm P và `cflowbelow` loại chính P.
- [ ] Đã xét số lần vào/ra P, tần suất tới Q, số advice match và chi phí advice.
- [ ] Đã kiểm tra recursion, exception, concurrency và async boundary.
- [ ] Chỉ bind/truy xuất runtime context thật sự cần sử dụng.
- [ ] Đã dùng workload và benchmark phù hợp, không để stdout/lifecycle khởi động làm sai số.
- [ ] Đã kiểm chứng tập join point trước và sau khi tối ưu bằng test chức năng.

**Kết luận:** chi phí pointcut động không phải chỉ là một lần kiểm tra boolean. Nó là tổng của việc duy trì ngữ cảnh flow, kiểm tra các join point ứng viên và thực thi advice thật sự. Phương pháp tốt là **đúng ngữ nghĩa trước, lọc tĩnh hẹp ở nơi có thể, tránh context động không cần thiết, rồi đo bằng workload đại diện**.

## Tài liệu tham khảo

- [AspectJ — Pointcuts](https://eclipse.dev/aspectj/doc/released/progguide/semantics-pointcuts.html): ngữ nghĩa `cflow`, `cflowbelow`, `if` và các designator khác.
- [AspectJ — Writing good pointcuts](https://eclipse.dev/aspectj/doc/latest/progguide/language.html): giới hạn phạm vi shadow và tối ưu matching.
- [AspectJ — Development Environment Guide](https://eclipse.dev/aspectj/doc/latest/devguide/devguide.html): sử dụng `ajc`, thông tin weaving.
- [AspectJ developers — Performance facts and tips](https://www.eclipse.org/lists/aspectj-dev/msg00551.html): heuristics về static/dynamic pointcut và tracking flow; cần kiểm tra lại bằng benchmark trên môi trường đang chạy.
