# Không dùng AtomicInteger chỉ để lách quy tắc effectively final

Khi bắt đầu dùng **lambda** trong Java, nhiều người gặp lỗi biên dịch do một biến cục bộ được tham chiếu trong lambda **không final hoặc effectively final**. Một cách “chữa cháy” hay gặp là thay biến int bằng **AtomicInteger**, rồi gọi incrementAndGet() hoặc addAndGet() bên trong lambda. Mã có thể biên dịch, nhưng đổi sang một container có thể thay đổi trạng thái **không giải quyết vấn đề thiết kế**: nó có thể tạo side effect, làm phép xử lý khó dự đoán và không tận dụng được các phép tổng hợp chuẩn của Stream.

Hãy phân biệt hai nhu cầu:

- **Cần tính một kết quả** như số phần tử, tổng tiền, số dòng hợp lệ hoặc kết quả nhóm: thường dùng **count, sum, reduce, collect** hoặc vòng lặp rõ ràng và trả giá trị.
- **Cần một trạng thái nguyên tử thực sự được chia sẻ giữa nhiều thread** như số tác vụ đã hoàn tất hoặc bộ đếm tiến độ: **AtomicInteger** có thể phù hợp, nhưng đó là yêu cầu đồng thời thực sự, không phải cách tránh thông báo lỗi capture variable.

Bài học này giải thích chính xác quy tắc **effectively final**, tại sao holder mutable có thể được lambda tham chiếu, những rủi ro khi dùng AtomicInteger sai chỗ, cách thay thế bằng phép tổng hợp thuần hoặc collector, và các trường hợp AtomicInteger là công cụ đúng. Mọi ví dụ độc lập dùng **Java 17+**.

## 1. Effectively final có nghĩa là gì?

Lambda có thể tham chiếu **biến cục bộ** và **tham số phương thức** từ phạm vi bao quanh nếu những biến đó là **final hoặc effectively final**.

~~~java
int minimum = 10;

List<Integer> values = List.of(3, 10, 15, 20);

long count = values.stream()
    .filter(number -> number >= minimum)
    .count();
~~~

Biến minimum không được khai báo bằng từ khóa final nhưng vẫn **effectively final** vì sau khi gán 10, nó không bị gán lại. Lambda được phép đọc giá trị này.

Nếu thêm một phép gán lại biến minimum:

~~~java
int minimum = 10;
minimum = 15;

long count = values.stream()
    .filter(number -> number >= minimum)
    .count();
~~~

Đoạn trên **không biên dịch**: minimum không còn effectively final. Thông báo biên dịch thường có dạng **local variables referenced from a lambda expression must be final or effectively final**.

Điều kiện ở đây là về **gán lại biến cục bộ được capture**, không phải câu lệnh lambda có thể hay không thể đọc mọi kiểu dữ liệu mutable. Java cho phép tham chiếu tới một đối tượng mutable qua biến cục bộ effectively final; chính sự cho phép đó dẫn đến việc một số người dùng AtomicInteger như một mẹo né ràng buộc.

### 1.1. final và effectively final

| Trường hợp | Có effectively final? | Lambda được capture? |
| --- | --- | --- |
| int limit = 10; rồi chỉ đọc | Có | Có |
| final int limit = 10; | Có và được khai báo final | Có |
| int limit = 10; sau đó limit++ | Không | Không |
| int limit = 10; sau đó limit = 20 | Không | Không |
| AtomicInteger counter = new AtomicInteger(); chỉ gọi incrementAndGet() | Biến tham chiếu counter có thể effectively final | Có |
| List<String> items = new ArrayList<>(); chỉ gọi items.add(...) | Biến tham chiếu items có thể effectively final | Có |

**Quan trọng:** Tính effectively final của **tham chiếu** không làm **đối tượng mà tham chiếu đó trỏ tới** trở thành immutable. AtomicInteger có thể tăng giá trị nội bộ, ArrayList có thể thêm phần tử, dù biến local giữ tham chiếu không bị gán lại.

### 1.2. Biến cục bộ chưa khởi tạo nhưng được gán đúng một lần

Một biến không nhất thiết phải có initializer ngay tại khai báo để được xem là effectively final:

~~~java
int minimum;
minimum = 10;

long count = values.stream()
    .filter(x -> x >= minimum)
    .count();
~~~

Nếu minimum được gán đúng một lần theo các quy tắc **definite assignment** và không có phép gán làm mất tính effectively final, cách sử dụng này có thể hợp lệ. Điểm cốt lõi không phải có từ khóa final, mà là **biến được gán theo cách tương thích với ràng buộc capture của Java**.

### 1.3. Đối tượng mutable khác với biến mutable

~~~java
List<String> result = new ArrayList<>();

Runnable action = () -> result.add("Java");
action.run();
~~~

Đoạn này **biên dịch**: bản thân biến result không bị gán lại. Nhưng **ArrayList được sửa**, nên lambda có side effect. Việc biên dịch thành công không chứng minh action là thuần, dễ dùng song song hoặc an toàn khi chia sẻ.

## 2. Vì sao Java đặt ra ràng buộc effectively final?

Biến cục bộ thông thường thuộc ngữ cảnh thực thi của phương thức. Lambda có thể được lưu lại và chạy **sau khi phương thức tạo nó đã kết thúc**, hoặc chạy ở thời điểm/thread khác.

Ví dụ:

~~~java
static Runnable makeAction() {
    int threshold = 10;

    return () -> System.out.println(threshold);
}
~~~

Runnable trả về vẫn có thể dùng giá trị threshold sau khi makeAction đã return. Java capture **giá trị của biến cục bộ effectively final** theo ngữ nghĩa phù hợp của lambda, chứ không chia sẻ một “ô biến local int” luôn được cập nhật bởi scope ban đầu.

Quy tắc effectively final giúp tránh sự mơ hồ khi một biến local có thể bị gán lại trong một scope còn lambda giữ giá trị cũ. Nó cũng ngăn một số nhầm lẫn về khả năng nhìn thấy thay đổi giữa các thread.

**Không nên suy luận rằng effectively final là một cơ chế đồng bộ thread.** Nó chỉ ràng buộc việc gán lại local/parameter được capture. Nếu tham chiếu trỏ tới trạng thái mutable dùng chung, vấn đề visibility, race và atomicity vẫn cần được giải quyết riêng.

### 2.1. Capture local khác truy cập field

Lambda có thể truy cập instance field hoặc static field. Các field không tuân theo cùng quy tắc capture local effectively final:

~~~java
class CounterHolder {
    int count;

    Runnable action() {
        return () -> count++;
    }
}
~~~

Mã này có thể biên dịch. Nhưng count++ trên field vẫn là một phép đọc-sửa-ghi không có bảo đảm an toàn đồng thời. Chuyển biến đếm sang field **không phải giải pháp tốt** chỉ nhằm né quy tắc capture; nó có thể làm state phân tán và khó kiểm soát hơn.

## 3. Anti-pattern: dùng AtomicInteger như một hộp int mutable

Ví dụ hay gặp:

~~~java
AtomicInteger count = new AtomicInteger();

items.forEach(item -> {
    if (isValid(item)) {
        count.incrementAndGet();
    }
});

System.out.println(count.get());
~~~

Đây là **mã minh họa** với items và isValid được giả định đã khai báo. Nó hợp lệ về cú pháp capture vì biến tham chiếu count không được gán lại. Nhưng nếu mục tiêu chỉ là **đếm các phần tử hợp lệ trong một Collection**, dùng AtomicInteger khiến kết quả bị truyền qua **side effect** thay vì biểu thức trả giá trị.

Cách trực tiếp hơn:

~~~java
long count = items.stream()
    .filter(this::isValid)
    .count();
~~~

Đoạn thứ hai cũng là mã minh họa đặt trong instance method có isValid thích hợp.

Những khác biệt:

- **Cách AtomicInteger:** callback sửa một object bên ngoài pipeline; phải nhìn cả biến đếm trước và sau forEach mới hiểu kết quả.
- **Cách count():** pipeline mô tả điều kiện lọc và terminal operation **trả kết quả số lượng**; không cần container trung gian.
- **Về kiểu:** count() trả **long**, có thể thích hợp hơn int nếu số lượng lớn.
- **Về tối ưu:** Stream được phép đánh giá pipeline theo hợp đồng; không có side effect cần thiết trong callback.
- **Về kiểm thử:** so sánh trực tiếp giá trị count với kết quả mong đợi, không cần khởi tạo/đặt lại holder dùng chung.

**Không nói AtomicInteger ở ví dụ đầu luôn sai về chức năng.** Nếu mọi callback chạy một lần và tăng biến thành công, nó có thể ra đúng số. Nhưng đó là một mô hình dư thừa và dễ dẫn tới sử dụng sai khi thay đổi pipeline.

## 4. Vì sao AtomicInteger không “sửa” thiết kế lambda?

AtomicInteger là lớp trong **java.util.concurrent.atomic**, hỗ trợ những thao tác nguyên tử trên một số nguyên: get(), set(), incrementAndGet(), getAndIncrement(), addAndGet(), compareAndSet(), updateAndGet(), v.v.

~~~java
AtomicInteger counter = new AtomicInteger(0);

counter.incrementAndGet();
System.out.println(counter.get()); // 1
~~~

Khi lambda capture biến counter:

~~~java
AtomicInteger counter = new AtomicInteger();

Consumer<String> action = text -> {
    counter.incrementAndGet();
};
~~~

Biến local counter **effectively final**, nhưng object AtomicInteger được sửa. Đây là **bọc trạng thái trong object** để bypass ràng buộc gán lại local, không biến phép tính thành một giá trị bất biến.

Cần phân biệt:

1. **Biên dịch được:** local reference không bị gán lại.
2. **Nguyên tử khi tăng:** incrementAndGet thực hiện một cập nhật atomic.
3. **Đúng nghĩa nghiệp vụ:** callback phải chạy đúng những lần được phép và giá trị đếm phải đại diện đúng mục tiêu.
4. **Thuần/không tác dụng phụ:** lambda có thay đổi trạng thái được quan sát ở ngoài hay không.
5. **An toàn cho quy trình lớn hơn:** những thao tác liên quan ngoài lần tăng có được phối hợp đúng hay không.

Một đoạn mã có thể đạt (1) và (2) nhưng **không đạt (3), (4) hoặc (5)**. Atomicity của increment không thay thế thiết kế thuật toán phù hợp.

### 4.1. AtomicInteger không biến callback thành pure function

Hàm thuần nên có kết quả xác định từ đầu vào và không có tác dụng phụ quan sát được. Callback gọi counter.incrementAndGet có **side effect**; cùng đầu vào nhưng trạng thái bộ đếm thay đổi qua các lần gọi.

~~~java
AtomicInteger calls = new AtomicInteger();

Function<String, String> normalize = text -> {
    calls.incrementAndGet();
    return text.trim();
};
~~~

Trên bề mặt normalize trả chuỗi mới, nhưng nó đồng thời sửa calls. Khi đem normalize vào stream, chương trình không còn chỉ quan tâm danh sách kết quả: nó vô tình phụ thuộc số lần callback được thực thi.

## 5. Stream có thể tối ưu và không gọi callback không cần thiết

Đây là lý do sâu hơn không nên đặt phép đếm side effect trong map hoặc peek.

~~~java
AtomicInteger observed = new AtomicInteger();

long count = List.of(1, 2, 3, 4).stream()
    .map(value -> {
        observed.incrementAndGet();
        return value * 2;
    })
    .count();
~~~

Với nguồn có kích thước biết trước và pipeline map **không thay đổi số phần tử**, Stream có thể tính count từ kích thước nguồn mà **không cần gọi mapper**. Theo hợp đồng Java Stream, các implementation được phép bỏ qua những callback nếu việc thực hiện chúng không ảnh hưởng kết quả terminal.

Do đó:

- count có kết quả đúng là 4.
- **Không được dùng observed.get() để khẳng định mapper đã xử lý đủ bốn phần tử.**
- Một số môi trường thực thi có thể bỏ qua map hoàn toàn đối với pipeline này.
- Thay map bằng peek để “bắt buộc” tăng counter cũng không giải quyết hợp đồng.

Đây không phải lỗi của AtomicInteger. Lỗi nằm ở giả định rằng **mọi intermediate callback luôn phải chạy** khi terminal được gọi.

### 5.1. filter, findFirst và short-circuit

~~~java
AtomicInteger visited = new AtomicInteger();

Optional<Integer> first = Stream.of(2, 4, 7, 9)
    .filter(value -> {
        visited.incrementAndGet();
        return value % 2 != 0;
    })
    .findFirst();
~~~

findFirst có thể dừng khi tìm thấy phần tử đầu tiên thỏa điều kiện, không cần kiểm tra toàn bộ nguồn. Trong một sequential ordered stream như ví dụ, ba phần tử 2, 4, 7 đủ để tìm kết quả 7.

Nhưng nếu chuyển sang parallel, đổi nguồn, thêm stateful operations hoặc một terminal khác, số lần và thứ tự callback không nên là hợp đồng của chương trình.

**Nếu cần kết quả “phần tử đầu tiên thỏa điều kiện”,** trả Optional từ findFirst. **Nếu cần số phần tử thỏa điều kiện,** dùng filter(...).count(). **Nếu cần đếm số callback vì mục đích quan sát runtime**, bộ đếm có thể là instrumentation tạm, nhưng không nên được dùng làm kết quả nghiệp vụ được cam kết.

### 5.2. Vấn đề khi dùng parallelStream

~~~java
AtomicInteger counter = new AtomicInteger();

values.parallelStream()
    .filter(this::accept)
    .forEach(value -> counter.incrementAndGet());
~~~

Ví dụ này có thể đếm các phần tử đến được terminal forEach, nếu mọi thao tác thành công; tăng bằng AtomicInteger tránh race mất lần tăng của một int dùng chung.

Nhưng nếu nhiệm vụ chỉ là đếm phần tử thỏa predicate thì:

~~~java
long count = values.parallelStream()
    .filter(this::accept)
    .count();
~~~

diễn đạt ý định tốt hơn, tránh thay đổi state trong callback và để Stream thực hiện reduction phù hợp. Việc gọi parallel không tự động khiến trường hợp AtomicInteger nhanh hơn: các update cùng một atomic counter có thể **tranh chấp (contention)**, làm nhiều worker chờ nhau.

## 6. Thay bộ đếm thủ công bằng terminal operation

### 6.1. Đếm phần tử

~~~java
long positiveCount = numbers.stream()
    .filter(x -> x > 0)
    .count();
~~~

Thay cho tăng AtomicInteger trong forEach.

### 6.2. Tính tổng

~~~java
int sum = numbers.stream()
    .mapToInt(Integer::intValue)
    .sum();
~~~

Thay cho:

~~~java
AtomicInteger sum = new AtomicInteger();
numbers.forEach(x -> sum.addAndGet(x));
~~~

Nếu tổng có thể vượt phạm vi int, dùng mapToLong(...).sum() khi phù hợp. Cả int và long đều có giới hạn; tùy nghiệp vụ, cần kiểm tra overflow hoặc dùng số có miền giá trị lớn hơn.

### 6.3. Đếm theo nhóm

~~~java
Map<String, Long> counts = employees.stream()
    .collect(Collectors.groupingBy(
        Employee::department,
        Collectors.counting()
    ));
~~~

Đoạn minh họa cần kiểu Employee có phương thức department() và import Map/Collectors. Không cần Map<String, AtomicInteger> được sửa bên ngoài callback.

Nếu muốn thống kê theo Map với thứ tự khóa xác định để kiểm thử output, có thể chọn TreeMap:

~~~java
Map<String, Long> ordered = employees.stream().collect(
    Collectors.groupingBy(
        Employee::department,
        TreeMap::new,
        Collectors.counting()
    )
);
~~~

### 6.4. Thu nhiều chỉ số bằng một collector

Nếu vừa cần số lượng vừa cần tổng, có thể dùng **Collectors.teeing** (Java 12+) để kết hợp hai downstream collectors:

~~~java
record Summary(long count, int total) {}

Summary summary = sales.stream().collect(Collectors.teeing(
    Collectors.counting(),
    Collectors.summingInt(Sale::amount),
    Summary::new
));
~~~

Đây là đoạn minh họa với record Sale phù hợp, có chương trình độc lập ở phần 11. Kết quả là một **giá trị Summary** tường minh, không phải hai AtomicInteger side effects bị cập nhật lẫn nhau.

## 7. Reduce thay vì biến tích lũy bên ngoài

Phép reduce gộp nhiều phần tử thành một kết quả theo quy tắc xác định.

~~~java
int total = numbers.stream()
    .reduce(0, Integer::sum);
~~~

Đối với stream tuần tự, có thể hình dung phép cộng bắt đầu từ 0 rồi gộp từng phần tử. Với parallel stream, phép reduction có thể được chia thành các kết quả cục bộ rồi ghép.

Vì vậy accumulator/combiner cần thích hợp về **identity**, **associativity** và, với reduce ba đối số, **compatibility**.

### 7.1. Không thay một lỗi bằng mutable identity khác

Không nên dùng:

~~~java
AtomicInteger identity = new AtomicInteger();

AtomicInteger total = numbers.parallelStream().reduce(
    identity,
    (counter, value) -> {
        counter.addAndGet(value);
        return counter;
    },
    (left, right) -> {
        left.addAndGet(right.get());
        return left;
    }
);
~~~

Dù các thao tác addAndGet nguyên tử, code dùng **identity mutable được chia sẻ**, làm sai mô hình reduction. Một nhóm có thể ghép với chính identity đã bị thay đổi, dẫn đến lặp cộng hoặc race; không thể sửa chỉ bằng việc gọi phương thức atomic.

**Tốt hơn:** dùng giá trị immutable như Integer/Long với phép cộng tương thích, hoặc dùng **collect** khi cần mutable accumulation:

~~~java
long total = numbers.parallelStream()
    .mapToLong(Integer::longValue)
    .sum();
~~~

Khi cần xây dựng ArrayList/StringBuilder có mutation nội bộ, sử dụng một Collector đúng hợp đồng với **supplier tạo container thích hợp** thay vì ép mutable object vào reduce.

### 7.2. Bộ tích lũy trong Stream khác shared mutable variable

Stream.reduce và các collector phù hợp có thể quản lý kết quả cục bộ theo hợp đồng. Người viết không cần cập nhật một biến counter toàn cục từ nhiều thread.

Điều đó giúp tách **logic phép tính** khỏi chi tiết **lịch chạy của các worker**, và giảm phụ thuộc vào atomic contention. Kết quả chỉ đúng nếu reducer/collector của bạn tuân thủ luật tương ứng; compiler không tự chứng minh các luật đại số này.

## 8. Dùng vòng lặp thông thường khi rõ ràng hơn

Lập trình hàm không phải quy tắc cấm mọi mutation.

Nếu thật sự có một thuật toán tuần tự gồm nhiều nhánh, một biến cục bộ cập nhật bên trong vòng lặp có thể đơn giản và đúng hơn một holder AtomicInteger:

~~~java
int validCount = 0;

for (Order order : orders) {
    if (isValid(order)) {
        validCount++;
    }
}
~~~

Đây là đoạn minh họa với kiểu Order và phương thức isValid phù hợp.

**Không có lambda capture local ở đây**, nên không có lý do phải đổi validCount thành AtomicInteger. Trong một hàm tuần tự, biến local không chia sẻ ra ngoài thường có phạm vi và chi phí dễ hiểu.

Có thể dùng vòng for khi:

- Cần break/continue hoặc nhiều nhánh điều khiển phức tạp.
- Cần cập nhật một trạng thái nhỏ trong phạm vi cục bộ có kiểm soát.
- Cần tương tác API imperative.
- Vòng lặp rõ hơn một pipeline Stream có nhiều lambda dài.

Mục tiêu không phải “một dòng Stream bằng mọi giá”, mà là **hợp đồng rõ ràng và mã dễ kiểm chứng**.

## 9. AtomicInteger phù hợp khi nào?

AtomicInteger được thiết kế cho trường hợp cần **cập nhật số nguyên atomically** từ các thread có thể hoạt động đồng thời hoặc một cấu trúc trạng thái yêu cầu compare-and-set.

Ví dụ hợp lý:

- Đếm số tác vụ đã hoàn thành từ nhiều worker thread.
- Cập nhật bộ đếm trạng thái chung của một dịch vụ đồng thời.
- Tạo sequence/ticket nội bộ đơn giản khi yêu cầu và ranh giới tràn số cho phép.
- Một số thuật toán lock-free sử dụng compareAndSet đúng hợp đồng.

Lúc này **trạng thái chia sẻ chính là yêu cầu**, không phải tác dụng phụ được thêm vào một phép tính vốn có thể trả giá trị.

### 9.1. Ví dụ: đếm số tác vụ hoàn thành

~~~java
AtomicInteger completed = new AtomicInteger();
ExecutorService pool = Executors.newFixedThreadPool(4);

try {
    List<Future<?>> futures = new ArrayList<>();

    for (int task = 0; task < 1000; task++) {
        futures.add(pool.submit(() -> {
            completed.incrementAndGet();
        }));
    }

    for (Future<?> future : futures) {
        future.get();
    }
} finally {
    pool.shutdown();
}

System.out.println(completed.get()); // 1000
~~~

Đoạn minh họa này đặt trong một phương thức khai báo hoặc xử lý các checked exceptions từ Future.get(), có import đầy đủ ở chương trình độc lập.

**Vì sao AtomicInteger có ý nghĩa tại đây?** Nhiều tác vụ thực sự chạy trên một pool có nhiều worker thread; cùng một biến completed đại diện cho bộ đếm trạng thái chia sẻ. incrementAndGet là cập nhật atomic, tránh lost update của count++ trên int chia sẻ.

Lời gọi Future.get() đợi từng tác vụ đã submit hoàn tất hoặc báo lỗi; sau khi tất cả future thành công, giá trị 1000 có ý nghĩa xác định trong ví dụ.

Nếu việc đếm chỉ là **số Future trong List** hoặc **số phần tử của một Stream đã biết**, không cần AtomicInteger; số tác vụ **đã hoàn thành theo thời gian** mới là lý do hợp lệ cho một counter đồng thời.

### 9.2. AtomicInteger không bảo đảm transaction nhiều bước

~~~java
if (counter.get() < limit) {
    counter.incrementAndGet();
}
~~~

Đoạn trên có **race** khi nhiều thread cùng thực hiện: phép get và incrementAndGet riêng lẻ là atomic, nhưng **điều kiện kiểm tra + cập nhật không phải một thao tác atomic tổng thể**. Nhiều thread có thể cùng thấy giá trị dưới limit rồi tăng vượt giới hạn.

Cần một thiết kế đồng bộ cho toàn bộ invariant, ví dụ vòng lặp compareAndSet, semaphore hoặc lock tùy tình huống. Không suy luận rằng mọi đoạn code chứa AtomicInteger đều tự động thread-safe.

### 9.3. LongAdder khi cập nhật thống kê nhiều lần

Trong những hệ thống có tần suất cập nhật bộ đếm cao và contention lớn, **LongAdder** có thể tăng throughput so với một AtomicLong duy nhất trong một số workload. Nhưng **sum() không phải snapshot atomic nhất quán** khi cập nhật diễn ra đồng thời.

Vì vậy LongAdder thường phù hợp cho metrics/statistics, không phải thay thế mặc định khi cần compare-and-set hoặc một giá trị sequence duy nhất có tính nhất quán tức thời.

## 10. updateAndGet và accumulateAndGet: lambda có thể được gọi lại

Một điểm nâng cao của AtomicInteger là các phương thức cập nhật dựa trên hàm:

~~~java
AtomicInteger value = new AtomicInteger(5);

int updated = value.updateAndGet(current -> current + 2);
System.out.println(updated); // 7
~~~

Những phương thức cập nhật kiểu **updateAndGet**, **getAndUpdate**, **accumulateAndGet**, **getAndAccumulate** có thể phải **gọi lại hàm cập nhật nhiều lần khi CAS thất bại do contention**.

Do đó **hàm cập nhật phải không có side effect**, vì một lần cập nhật thành công không đồng nghĩa lambda được gọi đúng một lần:

~~~java
AtomicInteger counter = new AtomicInteger();

counter.updateAndGet(current -> {
    sendEmail(); // Sai ý định: có thể bị gọi lại.
    return current + 1;
});
~~~

Đây là mã minh họa sai có chủ ý, với sendEmail là chức năng giả định, không phải Java API sẵn có.

**Tương phản thú vị:** AtomicInteger có thể là một thành phần đồng thời hữu ích, nhưng **ngay trong API của nó**, một số lambda cập nhật vẫn cần phong cách **thuần/stateless** để tránh lặp side effect. Đừng hiểu việc dùng atomic là giấy phép đặt mọi thao tác nghiệp vụ trong callback.

### 10.1. incrementAndGet và getAndIncrement

~~~java
AtomicInteger next = new AtomicInteger(10);

int oldValue = next.getAndIncrement(); // 10
int newValue = next.incrementAndGet(); // 12
~~~

Sau lời gọi đầu, nội bộ next thành 11; lời gọi thứ hai tăng lên 12 rồi trả 12. Khác biệt là **thời điểm trả giá trị cũ/mới**. Chọn đúng nếu triển khai sequence hoặc số thứ tự, và xem xét tràn int.

## 11. Chương trình Java 17+ hoàn chỉnh

Chương trình sau cố ý tách **hai loại tác vụ**.

Nhóm A: tính số giao dịch đạt ngưỡng, tổng tiền, tổng theo khu vực và thống kê chung. Chúng đều là **giá trị kết quả của Stream**; không cần AtomicInteger để lách effectively final.

Nhóm B: tạo một pool worker để chạy **1000 tác vụ đồng thời**. Các tác vụ dùng AtomicInteger để cập nhật số lượng hoàn thành **vì có trạng thái chia sẻ thực sự**.

Tạo tệp **AtomicCaptureDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class AtomicCaptureDemo {
    record Sale(String region, int amount) {}
    record Summary(long count, int total) {}

    public static void main(String[] args) throws Exception {
        List<Sale> sales = List.of(
            new Sale("North", 10),
            new Sale("South", 25),
            new Sale("North", 15),
            new Sale("South", 5)
        );

        int minimum = 10;
        long qualified = sales.stream()
            .filter(sale -> sale.amount() >= minimum)
            .count();
        int total = sales.stream()
            .mapToInt(Sale::amount)
            .sum();

        Map<String, Integer> byRegion = sales.stream().collect(
            Collectors.groupingBy(
                Sale::region,
                TreeMap::new,
                Collectors.summingInt(Sale::amount)
            )
        );
        Summary summary = sales.stream().collect(Collectors.teeing(
            Collectors.counting(),
            Collectors.summingInt(Sale::amount),
            Summary::new
        ));

        System.out.println("qualified=" + qualified);
        System.out.println("total=" + total);
        System.out.println("byRegion=" + byRegion);
        System.out.println("summary=" + summary);
        System.out.println("intSum=" + IntStream.rangeClosed(1, 5).sum());

        AtomicInteger completed = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Future<?>> futures = new ArrayList<>();
            for (int task = 0; task < 1000; task++) {
                futures.add(pool.submit(() -> {
                    completed.incrementAndGet();
                }));
            }
            for (Future<?> future : futures) {
                future.get();
            }
        } finally {
            pool.shutdown();
        }

        System.out.println("completedTasks=" + completed.get());
        System.out.println("originalSize=" + sales.size());
    }
}
~~~

Biên dịch/chạy trên **JDK 17 trở lên**:

~~~bash
javac AtomicCaptureDemo.java
java AtomicCaptureDemo
~~~

**Stdout chính xác đã kiểm chứng:**

~~~text
qualified=3
total=55
byRegion={North=25, South=30}
summary=Summary[count=4, total=55]
intSum=15
completedTasks=1000
originalSize=4
~~~

### 11.1. Phân tích kết quả

**qualified=3:** Có ba Sale có amount >= 10 (10, 25 và 15); terminal count() trả số phần tử thỏa điều kiện mà không dùng mutable counter.

**total=55:** Các amount cộng lại thành 10+25+15+5=55. mapToInt().sum() trả kết quả trực tiếp.

**byRegion:** groupingBy với TreeMap::new và summingInt trả Map<String,Integer>. North có 10+15=25; South có 25+5=30. TreeMap giúp thứ tự khóa hiển thị có thể dự đoán.

**summary:** teeing kết hợp counting() và summingInt() thành record Summary(count=4,total=55), thay thế hai holder mutable ngoài pipeline.

**intSum=15:** Tổng các số 1..5 được tính bằng IntStream.sum; không cần AtomicInteger.

**completedTasks=1000:** 1000 Runnable được gửi đến ExecutorService có bốn worker. Mỗi tác vụ hoàn thành phép tăng một lần. Future.get đợi tác vụ tương ứng kết thúc, nên sau khi tất cả future trả thành công, completed có giá trị 1000. Chính sự chia sẻ trạng thái giữa worker threads làm AtomicInteger phù hợp.

**originalSize=4:** Stream terminal operations không sửa List nguồn trong ví dụ. AtomicInteger được dùng ở phần điều phối tác vụ chứ không tác động đến dữ liệu Sale.

### 11.2. Đây không phải hệ thống điều phối production đầy đủ

Ví dụ chọn pool cố định để kết quả dễ kiểm tra. Trong ứng dụng thật cần thiết kế chính sách **hủy tác vụ, retry, interrupt, shutdown/awaitTermination, xử lý exception, giới hạn số task, áp lực bộ nhớ** và đảm bảo không tăng trùng nếu một thao tác được retry. Một counter atomic riêng lẻ không tạo bảo đảm exactly-once ở mức hệ thống phân tán.

Nếu trình biên dịch hoặc runner chỉ có JDK 17, ví dụ sử dụng đúng record và Collectors.teeing đã hỗ trợ.

## 12. Phân biệt AtomicInteger, int[], field và biến local

Có những cách “lách capture” khác cũng cần tránh:

### 12.1. Mảng một phần tử làm holder

~~~java
int[] counter = {0};

values.forEach(value -> counter[0]++);
~~~

Mã có thể biên dịch, vì tham chiếu counter không được gán lại. Nhưng **counter[0]++ không atomic** và có thể bị lost update trong xử lý đồng thời. Việc đổi int thành int[] không tự bảo đảm thread-safety hay làm lambda thuần.

### 12.2. Field được sửa từ lambda

~~~java
class Processor {
    int count;

    void process(List<Integer> values) {
        values.forEach(value -> count++);
    }
}
~~~

Field không chịu ràng buộc capture local như một biến local, nhưng **trạng thái sống lâu hơn phương thức và có thể chia sẻ qua lời gọi/luồng**, khiến kết quả phụ thuộc lịch sử thực thi. Nếu chỉ đếm phần tử, hãy trả long từ phương thức.

### 12.3. AtomicInteger là holder mutable có đồng bộ nguyên tử

~~~java
AtomicInteger counter = new AtomicInteger();
values.forEach(value -> counter.incrementAndGet());
~~~

Cập nhật counter là atomic, nhưng code vẫn làm side effect. Chỉ dùng khi **chính trạng thái chia sẻ** là yêu cầu; không chọn nó làm phương án mặc định cho một phép tổng hợp thuần.

### 12.4. int cục bộ trong vòng for

~~~java
int count = 0;
for (int value : values) {
    count++;
}
~~~

Không có capture, không có object holder và kết quả rõ ràng. Trong ngữ cảnh tuần tự, có thể là lựa chọn tốt nếu vòng lặp đơn giản hơn Stream.

## 13. Vấn đề về lỗi và việc dừng pipeline

Khi callback ném ngoại lệ, terminal operation có thể không hoàn tất. Bộ đếm side effect khi ấy có thể chỉ phản ánh **một phần quá trình**, khó phân biệt với một kết quả nghiệp vụ hợp lệ.

Ví dụ:

~~~java
AtomicInteger counter = new AtomicInteger();

try {
    Stream.of("10", "bad", "20")
        .map(Integer::parseInt)
        .forEach(value -> counter.incrementAndGet());
} catch (NumberFormatException error) {
    System.out.println("invalid input");
}
~~~

Nếu NumberFormatException xuất hiện ở phần tử "bad", terminal thất bại; counter không phải số phần tử toàn bộ đã được xử lý thành công theo một giao dịch hoàn chỉnh. Trình tự chạy có thể phụ thuộc nguồn và chế độ stream.

Nếu cần **xử lý được lỗi từng bản ghi**, hãy thiết kế giá trị kết quả biểu diễn thành công/thất bại, hoặc áp dụng validation trước khi tổng hợp. Không dựa vào AtomicInteger như nguồn chân lý cho trạng thái xử lý toàn bộ pipeline.

### 13.1. Khi cần đếm số sự kiện đã nhận

Trong một consumer/event handler chạy dài hạn, trạng thái tiến độ thực sự có thể cần được cập nhật khi **mỗi sự kiện được hệ thống xử lý/commit**. AtomicInteger có thể thích hợp để phản ánh số sự kiện, nhưng phải định nghĩa rõ điểm được xem là hoàn tất và chính sách retry/duplicate. Đó là bài toán đồng thời và độ tin cậy, không phải bài toán capture trong lambda.

## 14. Hiệu năng và khả năng bảo trì

Việc dùng một AtomicInteger chung trong parallelStream có thể dẫn đến **contention**: nhiều thread liên tục cập nhật cùng địa chỉ bộ nhớ. Với những reduction có thể phân chia, một phép count/sum/collect thường trao quyền quản lý kết quả cục bộ và ghép cho thư viện Stream.

Tuy nhiên, không nên tuyên bố Stream luôn nhanh hơn vòng for hoặc AtomicInteger trong mọi workload. Hiệu năng phụ thuộc kích thước dữ liệu, boxing, callback, parallelism, kích thước bộ nhớ, chiến lược chia và phần cứng.

**Đánh giá theo ba tiêu chí:**

1. **Correctness:** kết quả có phụ thuộc side effect, thứ tự callback, lỗi hay trạng thái chia sẻ không?
2. **Readability:** người đọc có thấy trực tiếp “đếm”, “cộng”, “nhóm” từ terminal/collector không?
3. **Performance:** sau khi logic đúng, có benchmark/profiling xác nhận cách triển khai phù hợp không?

Không đánh đổi correctness để cố viết lambda ngắn hoặc để biên dịch qua ràng buộc effectively final.

## 15. Checklist khi review lambda có AtomicInteger

| Câu hỏi | Cách đánh giá |
| --- | --- |
| Vì sao có AtomicInteger? | Có trạng thái chia sẻ thực sự cần cập nhật nguyên tử không? |
| Có phải chỉ muốn đếm số phần tử? | Ưu tiên filter(...).count() |
| Có phải muốn tính tổng? | Ưu tiên mapToInt/Long(...).sum() hoặc reduce phù hợp |
| Có phải muốn nhóm/thu nhiều giá trị? | Ưu tiên collect và downstream collectors |
| Có dùng trong map/peek/filter? | Cẩn thận callback bị tối ưu hoặc short-circuit |
| Có dùng parallelStream? | Kiểm tra side effect, contention và thứ tự |
| Biến local thực sự cần gán lại? | Xem cách tổ chức kết quả thay vì mutable holder |
| Có thể dùng vòng lặp đơn giản? | Không cần lambda hay AtomicInteger nếu không có concurrency |
| Update gồm nhiều bước? | AtomicInteger không tự bảo đảm invariant nhiều thao tác |
| Có dùng updateAndGet? | Function cập nhật cần không có side effect vì có thể retry |
| Có xử lý overflow? | Kiểm tra giới hạn int; chọn long/cấu trúc khác nếu cần |
| Test có phụ thuộc số callback? | Dùng kết quả nghiệp vụ, không suy đoán lịch chạy |

## 16. Những lỗi thường gặp

**Lỗi 1 — thay int bằng AtomicInteger chỉ để compile:** giải quyết triệu chứng compiler nhưng thêm mutation và side effect.

**Lỗi 2 — nghĩ effectively final nghĩa object immutable:** chỉ hạn chế gán lại biến capture; nội dung object có thể mutable.

**Lỗi 3 — nghĩ AtomicInteger biến callback thành pure function:** incrementAndGet sửa trạng thái được quan sát từ ngoài.

**Lỗi 4 — dùng map/peek tăng counter rồi count:** Stream có thể bỏ qua callback không làm thay đổi số phần tử.

**Lỗi 5 — nghĩ parallel forEach cho thứ tự xác định:** parallel forEach không bảo đảm encounter order; không gắn sequence theo thứ tự nguồn chỉ bằng incrementAndGet.

**Lỗi 6 — dùng một AtomicInteger làm identity trong reduce:** mutable identity chia sẻ có thể phá hợp đồng reduction dù phép cộng riêng lẻ là atomic.

**Lỗi 7 — dùng int[] một phần tử thay AtomicInteger:** phép ++ trên phần tử mảng không atomic và vẫn là side effect.

**Lỗi 8 — chuyển biến local thành field:** kéo dài vòng đời state, tăng nguy cơ kết quả phụ thuộc lịch sử hoặc cạnh tranh giữa lời gọi.

**Lỗi 9 — cho rằng atomicity của increment đủ cho mọi invariant:** check-then-act hai bước vẫn có race.

**Lỗi 10 — side effect trong updateAndGet:** hàm có thể bị gọi lại khi CAS retry, làm gửi email/ghi log trùng.

**Lỗi 11 — lấy counter sau một pipeline thất bại như kết quả thành công:** xử lý có thể đã dừng giữa chừng.

**Lỗi 12 — đếm số phần tử bằng forEach thay vì count:** làm việc thừa, tạo holder không cần thiết và giảm tính khai báo.

**Lỗi 13 — nghĩ lambda luôn chạy một lần cho từng phần tử:** còn có short-circuit, tối ưu hóa và những phép trung gian có trạng thái.

**Lỗi 14 — coi AtomicInteger luôn nhanh hơn:** nhiều luồng có thể tranh chấp cùng một atomic variable; LongAdder có trade-off khác.

**Lỗi 15 — xem mọi mutation là lỗi:** mutation cục bộ trong vòng for hoặc container của Collector có thể hợp lý; vấn đề là **đột biến ngầm của trạng thái chia sẻ** khi chỉ cần một phép tính trả giá trị.

## 17. Câu hỏi tự kiểm tra

1. Thế nào là effectively final, và nó khác từ khóa final ra sao?
2. Vì sao lambda đọc local int chưa gán lại được biên dịch, còn lambda tăng local int++ thì không?
3. Vì sao AtomicInteger được capture hợp lệ dù giá trị bên trong được increment?
4. Sự khác nhau giữa final reference và immutable object là gì?
5. Vì sao dùng AtomicInteger trong Stream.map rồi Stream.count có thể không đếm được số callback?
6. Khi cần số phần tử thỏa một predicate, cách nào tự nhiên hơn một AtomicInteger bên ngoài?
7. Khi cần tổng số tiền, làm sao dùng mapToLong hoặc reduce để trả kết quả?
8. Vì sao dùng AtomicInteger làm identity của reduce ba đối số có thể sai ngay cả khi addAndGet atomic?
9. Khi nào một biến int cục bộ trong vòng for rõ ràng hơn Stream?
10. Hãy nêu một tình huống nhiều worker thread cập nhật một trạng thái được chia sẻ mà AtomicInteger là lựa chọn thích hợp.
11. Vì sao get() rồi incrementAndGet() không tạo ra một điều kiện-ghi atomic tổng thể?
12. Vì sao lambda trong updateAndGet không nên gửi email hoặc ghi dữ liệu ngoài?
13. LongAdder khác AtomicInteger về mục tiêu throughput và tính nhất quán khi đọc như thế nào?
14. Vì sao AtomicInteger không tự ngăn pipeline có side effect hoặc data race trên những dữ liệu khác?
15. Nếu callback ném lỗi giữa pipeline, tại sao counter ngoài không nhất thiết là kết quả nghiệp vụ hoàn chỉnh?
16. Trong chương trình Java ở phần 11, đâu là những phép tổng hợp chỉ trả giá trị, và đâu là trạng thái chia sẻ thực sự?
17. Làm thế nào thử nghiệm và đo hiệu năng mà không phụ thuộc vào số lần map/peek callback được optimizer gọi?

**Kết luận:** **Effectively final** là quy tắc capture biến local của Java, không phải lời mời dùng AtomicInteger như một hộp int mutable. Khi cần tính số lượng, tổng, nhóm hoặc thống kê trong Stream, hãy **trả kết quả bằng count/sum/reduce/collect** và giữ callback tránh can thiệp trạng thái ngoài. Chỉ sử dụng AtomicInteger khi **chính bài toán cần trạng thái số nguyên được cập nhật nguyên tử giữa những hoạt động đồng thời**, với các invariant, lỗi, retry và giới hạn được thiết kế rõ ràng.