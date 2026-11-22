# collectList, collectMap, reduce và scan trong Project Reactor

## 1. Bốn toán tử dùng để làm gì?

Một **Flux<T>** trong Spring WebFlux/Project Reactor có thể phát nhiều phần tử theo thời gian. Khi xử lý đơn hàng, bản ghi cơ sở dữ liệu hoặc sự kiện, ứng dụng thường muốn một trong bốn dạng kết quả:

1. **Giữ tất cả phần tử** thành một List để trả response hoặc xử lý theo lô.
2. **Lập bảng tra cứu** Map theo một khóa được chọn từ từng phần tử.
3. **Tính một giá trị tổng hợp cuối cùng**, chẳng hạn tổng tiền hay số lớn nhất.
4. **Phát giá trị tổng hợp sau mỗi bước**, ví dụ tổng doanh thu đang chạy hoặc tiến độ hiện tại.

Bốn toán tử tương ứng:

| Toán tử | Kiểu trả về điển hình | Cách phát kết quả |
| --- | --- | --- |
| **collectList()** | Mono<List<T>> | Phát một List chứa các phần tử khi nguồn hoàn tất thành công |
| **collectMap(...)** | Mono<Map<K,V>> | Phát một Map khi nguồn hoàn tất thành công |
| **reduce(...)** | Mono<T> hoặc Mono<A> | Phát một kết quả tích lũy cuối khi nguồn hoàn tất |
| **scan(...)** | Flux<T> hoặc Flux<A> | Phát các trạng thái tích lũy trung gian khi phần tử đến |

**Điểm phân biệt quyết định:** collectList, collectMap và reduce cần **onComplete** để có kết quả cuối; scan có thể phát kết quả **trước khi onComplete**. Các toán tử này chỉ đổi cách biểu diễn/điều phối dữ liệu; chúng không tự làm nguồn vô hạn trở thành hữu hạn và không tự bảo đảm đầu vào vừa bộ nhớ.

### Ví dụ nhìn nhanh

~~~text
Nguồn:              2 ─── 3 ─── 5 ─── onComplete

collectList:                      [2,3,5] ─── onComplete
reduce(sum):                      10 ──────── onComplete
scan(sum):           2 ─── 5 ─── 10 ──────── onComplete
scan(0, sum):        0 ─── 2 ─── 5 ─── 10 ─ onComplete
~~~

**collectMap** cũng chờ nguồn hoàn tất, nhưng kết quả là các cặp key → value, không phải danh sách hay tổng số.

## 2. collectList: gom mọi phần tử thành một List

### Cú pháp, dòng dữ liệu và kiểu

~~~java
Flux<Integer> source = Flux.just(4, 2, 8, 2);
Mono<List<Integer>> result = source.collectList();
~~~

Phần trên là đoạn mã minh họa dùng trong một chương trình đã có import Reactor. Khi subscribe result, các giá trị của source được gom vào List; khi Flux hoàn tất thành công, Mono phát:

~~~text
[4, 2, 8, 2]
~~~

**collectList** giữ lại các giá trị trùng lặp và thứ tự **onNext thực tế**. Nếu nguồn phát 4,2,8,2 thì List có đúng bốn phần tử theo thứ tự đó. Nhưng nếu trước collectList dùng **flatMap** cho các tác vụ bất đồng bộ, thứ tự kết quả có thể khác thứ tự đầu vào; collectList không tự sắp xếp lại.

Các trường hợp biên:

- **Nguồn rỗng:** Flux.empty().collectList() phát **List rỗng** (một onNext chứa danh sách rỗng), rồi onComplete.
- **Nguồn lỗi:** upstream onError khiến Mono báo lỗi; List đã thu một phần **không** được phát như kết quả thành công.
- **Nguồn bị hủy:** việc hủy trước khi hoàn tất nghĩa là không có List cuối cho subscription đó.
- **Nguồn không kết thúc:** chưa có List cuối để phát, trừ khi nguồn được kết thúc/giới hạn bởi điều kiện khác.

### Khi nào nên dùng?

Dùng cho một **tập hữu hạn với kích thước được kiểm soát**: 20 sản phẩm mới nhất, trang kết quả tìm kiếm, danh sách lựa chọn, dữ liệu cần truyền cho thuật toán nhận List.

Ví dụ controller WebFlux trong dự án đã có ProductDto và productService:

~~~java
@GetMapping("/products")
public Mono<List<ProductDto>> listProducts() {
    return productService.findRecentProducts()
            .map(ProductDto::from)
            .take(100)
            .collectList();
}
~~~

**take(100)** giới hạn tối đa 100 phần tử được gom trên pipeline, nhưng nếu yêu cầu phân trang ổn định, vẫn phải thiết kế truy vấn có điều kiện/sắp xếp và phân trang ở data source. Không nên dựa hoàn toàn vào take để thay thế truy vấn hiệu quả.

### Rủi ro bộ nhớ

List phải giữ các phần tử cho đến lúc nguồn hoàn tất. Với n phần tử, lượng giữ lại thường tăng theo **O(n)** tham chiếu cộng kích thước dữ liệu/đối tượng. **Mono<List<T>>** tuy chỉ phát một giá trị nhưng giá trị đó có thể rất lớn. Nếu nguồn phát mãi, việc tích lũy không có giới hạn có thể gây áp lực heap/GC hoặc OutOfMemoryError.

Đối với dữ liệu lớn, cân nhắc phân trang, xử lý streaming, **buffer(size)**, **window(size)** hoặc tính trực tiếp thống kê với reduce. Khi cần chỉ 1.000 phần tử mới nhất, giới hạn nguồn và chính sách lấy mẫu phải phù hợp nghiệp vụ.

## 3. collectMap: chuyển Flux thành bảng tra cứu

### Những overload thường dùng

~~~java
record Product(String sku, String name) {}

Flux<Product> products = Flux.just(
        new Product("P01", "Bút"),
        new Product("P02", "Sổ")
);

// Khóa là SKU, giá trị là nguyên Product.
Mono<Map<String, Product>> bySku =
        products.collectMap(Product::sku);

// Khóa là SKU, giá trị chỉ là tên.
Mono<Map<String, String>> namesBySku =
        products.collectMap(Product::sku, Product::name);
~~~

Đây là đoạn mã minh họa. Hàm **keyExtractor** quyết định khóa; overload nhận **valueExtractor** quyết định phần giá trị. Kết quả chỉ được phát sau onComplete của products. Với nguồn rỗng, kết quả là Map rỗng, không phải Mono.empty().

### Khóa trùng nhau: phần tử phát sau ghi đè phần tử trước

~~~text
Product("P01", "Bút xanh")
Product("P02", "Sổ")
Product("P01", "Bút đỏ")
onComplete
~~~

**collectMap(Product::sku, Product::name)** cho:

~~~text
P01 -> "Bút đỏ"
P02 -> "Sổ"
~~~

Bởi vì P01 xuất hiện lần thứ hai nên giá trị sau thay thế giá trị trước. **collectMap không tự tính tổng, không giữ tất cả bản ghi trùng khóa, không tự chọn bản ghi mới nhất theo timestamp.** Nó giữ phần tử đến sau theo thứ tự tín hiệu onNext của upstream.

Nếu cần tất cả phần tử của từng khóa, **collectMultimap** là một lựa chọn:

~~~java
Mono<Map<String, java.util.Collection<Product>>> allBySku =
        products.collectMultimap(Product::sku);
~~~

Nếu cần tổng tiền theo khóa, dùng **collect(Supplier, BiConsumer)**, nhóm rồi tổng hợp, hoặc **GROUP BY** ở tầng cơ sở dữ liệu. Ví dụ đầy đủ về tổng theo khóa ở phần sau.

### Thứ tự Map và mapSupplier

Map mặc định của collectMap là một Map dạng hash; **không nên dựa vào thứ tự duyệt khóa**. Reactor có overload:

~~~java
Mono<Map<String, String>> sorted =
        products.collectMap(
                Product::sku,
                Product::name,
                java.util.TreeMap::new
        );
~~~

**TreeMap** tạo thứ tự khóa tăng dần đối với String. **LinkedHashMap** hữu ích nếu muốn giữ thứ tự chèn khóa. Đối với một Map bất biến cho từng subscription, hãy để Supplier tạo container mới; không dùng một Map mutable được chia sẻ ngầm giữa các subscription.

### Chi phí

collectMap cần giữ ít nhất các cặp khóa/giá trị còn tồn tại, nên chi phí bộ nhớ tăng theo số khóa phân biệt **k** và kích thước giá trị. Khi mọi phần tử có khóa khác nhau, k có thể bằng tổng số phần tử n. Với nguồn không hoàn tất, Map có thể cứ lớn dần mà không phát kết quả cuối.

## 4. reduce: một kết quả cuối cùng của phép tích lũy

### reduce(aggregator) không có seed

~~~java
Mono<Integer> total =
        Flux.just(2, 3, 5).reduce(Integer::sum);
~~~

Bên trong toán tử:

~~~text
Bắt đầu: acc = 2
Nhận 3:  acc = 2 + 3 = 5
Nhận 5:  acc = 5 + 5 = 10
Nguồn onComplete → Mono phát 10
~~~

Ở overload **reduce(BiFunction<T,T,T>)**, phần tử đầu tiên trở thành trạng thái khởi tạo, vì thế:

- **0 phần tử:** Mono kết thúc rỗng (**Mono.empty()**), không phát số 0.
- **1 phần tử:** Mono phát chính phần tử đó; aggregator không cần chạy.
- **N phần tử:** mỗi phần tử sau phần tử đầu kết hợp với trạng thái trước; Mono chỉ phát kết quả cuối khi nguồn hoàn tất.

Nếu source onError, reduce báo lỗi; không phát một tổng “thành công một phần” mặc định.

### reduce(seed, accumulator) có seed

~~~java
Mono<Integer> total =
        Flux.just(2, 3, 5).reduce(100, Integer::sum);
// Kết quả: 110

Mono<Integer> emptyWithSeed =
        Flux.<Integer>empty().reduce(100, Integer::sum);
// Kết quả: 100
~~~

Seed là trạng thái tích lũy ban đầu. Với nguồn rỗng, seed vẫn trở thành kết quả Mono:

| Nguồn | reduce(Integer::sum) | reduce(0, Integer::sum) |
| --- | --- | --- |
| 2, 3, 5 | 10 | 10 |
| 5 | 5 | 5 |
| Rỗng | Mono.empty() | Mono phát 0 |

Vì thế, nếu nghiệp vụ cần “tổng bằng 0” thay vì “không có dữ liệu”, chọn seed 0 hoặc quy tắc default rõ ràng. Nếu “không có bản ghi” phải phân biệt với “tổng hợp bằng 0”, cần giữ trường hợp Mono.empty() hoặc một kiểu kết quả có trạng thái.

### Kiểu trạng thái có thể khác kiểu phần tử

~~~java
record Sale(String sku, long cents) {}

Mono<Long> totalCents = Flux.just(
        new Sale("A", 2000),
        new Sale("B", 3500)
).reduce(0L, (sum, sale) -> sum + sale.cents());
// Kết quả 5500L
~~~

**Sale** là đầu vào, **Long** là kết quả. Điều này hữu ích cho count, tổng tiền, trạng thái tổng hợp nhiều trường và các phép biến đổi nghiệp vụ.

### Tính đúng đắn của accumulator

Nên ưu tiên hàm tích lũy dễ hiểu, có tính chất rõ ràng, không side effect:

~~~java
Flux.just(2, 3, 5).reduce(0, Integer::sum);
~~~

Không nên cập nhật biến mutable đặt **bên ngoài** Publisher nếu nhiều subscription có thể chạy đồng thời. Nếu seed là List/Map mutable, truyền **một đối tượng seed có sẵn** vào reduce(seed, ...) có thể gây chia sẻ trạng thái không mong muốn qua nhiều subscription. Khi cần seed mới cho từng lượt đăng ký, dùng **reduceWith(Supplier<A>, accumulator)**. Với mục tiêu xây container mutable, **collect(Supplier, BiConsumer)** thường diễn đạt ý định tốt hơn.

**reduce không tự chạy song song**. Một hàm không kết hợp được hoặc phụ thuộc thứ tự có thể sinh kết quả khác khi upstream đổi thứ tự phát. Với phép tính tiền cần độ chính xác, thường dùng **BigDecimal** hoặc số nguyên đơn vị nhỏ thay vì float/double.

## 5. scan: các trạng thái tích lũy liên tiếp

### scan(aggregator) không seed

~~~java
Flux<Integer> running =
        Flux.just(2, 3, 5).scan(Integer::sum);
// Phát lần lượt: 2, 5, 10
~~~

Cùng phép cộng với reduce, nhưng scan phát **mỗi trạng thái tích lũy**:

~~~text
onNext(2)  → phát 2
onNext(3)  → phát 5
onNext(5)  → phát 10
onComplete → kết thúc
~~~

**scan(BiFunction<T,T,T>)** lấy phần tử đầu làm kết quả đầu tiên; nguồn rỗng thì không phát giá trị nào. Với nguồn có n phần tử và hoàn tất bình thường, scan không seed phát n trạng thái.

### scan(seed, accumulator): phát cả seed ban đầu

~~~java
Flux<Integer> running =
        Flux.just(2, 3, 5).scan(100, Integer::sum);
// Phát: 100, 102, 105, 110
~~~

**scan(seed, ...)** phát seed **ngay như trạng thái đầu** khi subscription có demand; sau đó phát một kết quả mới cho từng phần tử nguồn. Với n phần tử, kết quả có **n + 1 trạng thái**. Với nguồn rỗng, scan(seed,...) vẫn phát **seed** và hoàn tất.

Nếu chỉ muốn trạng thái **sau khi xử lý ít nhất một dữ liệu**, có thể dùng:

~~~java
Flux<Integer> postEventTotals =
        Flux.just(2, 3, 5)
            .scan(100, Integer::sum)
            .skip(1);
// Phát: 102, 105, 110
~~~

Cần quyết định rõ UI/API có muốn hiện giá trị khởi tạo hay không; nếu quên, rất dễ xuất hiện lỗi thừa một phần tử.

### scanWith: tạo seed theo subscription

~~~java
Flux<Long> running =
        Flux.just(2L, 3L, 5L)
            .scanWith(() -> 100L, Long::sum);
// Phát: 100, 102, 105, 110
~~~

**scanWith(Supplier, accumulator)** khởi tạo seed theo từng subscription. Với seed là object mutable, cần tạo object độc lập theo lượt đăng ký. Nhưng ngay cả khi seed độc lập, việc **phát nhiều lần cùng một đối tượng mutable rồi sửa nó** có thể khiến Subscriber giữ tham chiếu cũ nhìn thấy nội dung mới; dùng immutable snapshot hoặc copy đúng cách khi cần.

### Khi nào nên dùng scan?

Phù hợp cho tổng tiền đang chạy, tiến độ nhập dữ liệu, số phần tử đã xử lý, trạng thái stream và thống kê liên tục. Khác với reduce, scan có thể phát các trạng thái trước khi nguồn kết thúc.

Tuy nhiên, scan **không tự lưu trạng thái bền vững**. Nếu muốn khôi phục sau crash, cần DB/broker/checkpoint. Với trạng thái tích lũy là List/Map tăng dần, scan vẫn có nguy cơ dùng ngày càng nhiều bộ nhớ, dù kết quả của nó phát liên tục.

## 6. So sánh chính xác kết quả khi nguồn rỗng, có lỗi hoặc không kết thúc

| Trạng thái nguồn | collectList | collectMap | reduce không seed | reduce có seed | scan không seed | scan có seed |
| --- | --- | --- | --- | --- | --- | --- |
| **Rỗng + onComplete** | List rỗng | Map rỗng | Mono.empty() | Phát seed | Flux rỗng | Phát seed |
| **Một phần tử + complete** | List một phần tử | Map một khóa | Phát phần tử đó | Phát trạng thái seed+phần tử | Phát phần tử đó | Phát seed và trạng thái sau phần tử |
| **N phần tử + complete** | Một List N phần tử | Một Map theo khóa | Một kết quả cuối | Một kết quả cuối | N kết quả trung gian | N+1 kết quả gồm seed |
| **onError** | Không phát List cuối; chuyển onError | Không phát Map cuối; chuyển onError | Không phát tổng cuối; chuyển onError | Không phát tổng cuối; chuyển onError | Có thể đã phát một số trạng thái rồi onError | Có thể đã phát seed/trạng thái rồi onError |
| **Không hoàn tất** | Chưa có List cuối | Chưa có Map cuối | Chưa có tổng cuối | Chưa có tổng cuối | Có thể tiếp tục phát từng tổng | Có thể tiếp tục phát từng tổng |

Ví dụ về lỗi:

~~~java
Flux<Integer> source = Flux.concat(
        Flux.just(2, 3),
        Flux.error(new IllegalStateException("broken"))
);

Mono<List<Integer>> list = source.collectList();  // onError
Mono<Integer> sum = source.reduce(Integer::sum); // onError
Flux<Integer> progress = source.scan(Integer::sum);
// progress có thể phát 2, 5, rồi onError.
~~~

Đây là đoạn minh họa; đừng coi các trạng thái trung gian trước onError là giao dịch đã được commit. Nếu nghiệp vụ cần kết quả bền vững, thiết kế lưu trữ/transaction riêng.

## 7. Chương trình Java 17+ chạy được: ví dụ đầy đủ

Ví dụ dùng dữ liệu bán hàng hữu hạn, hai nhóm hàng xuất hiện lặp lại để làm rõ sự khác nhau giữa **lấy giá trị cuối theo khóa** và **cộng dồn tất cả giá trị**. Chương trình dùng Reactor Core; **không cần chạy Spring Boot** để học các toán tử này.

Cấu trúc:

~~~text
reactor-aggregate-demo/
├── pom.xml
└── src/main/java/AggregationDemo.java
~~~

Tệp **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-aggregate-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>AggregationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp **src/main/java/AggregationDemo.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import reactor.core.publisher.Flux;

public class AggregationDemo {
    record Sale(String category, int amount) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("books", 10),
                new Sale("pens", 20),
                new Sale("books", 15),
                new Sale("pens", 7)
        );

        Flux<Sale> source = Flux.fromIterable(sales);

        List<Integer> amounts = source
                .map(Sale::amount)
                .collectList()
                .block();
        System.out.println("collectList = " + amounts);

        Map<String, Integer> lastByCategory = source
                .collectMap(Sale::category, Sale::amount, TreeMap::new)
                .block();
        System.out.println("collectMap = " + lastByCategory);

        Integer sum = source.map(Sale::amount)
                .reduce(Integer::sum)
                .block();
        System.out.println("reduce = " + sum);

        Integer sumWithSeed = source.map(Sale::amount)
                .reduce(100, Integer::sum)
                .block();
        System.out.println("reduce(seed) = " + sumWithSeed);

        List<Integer> running = source.map(Sale::amount)
                .scan(Integer::sum)
                .collectList()
                .block();
        System.out.println("scan = " + running);

        List<Integer> runningWithSeed = source.map(Sale::amount)
                .scan(100, Integer::sum)
                .collectList()
                .block();
        System.out.println("scan(seed) = " + runningWithSeed);

        System.out.println("empty collectList = "
                + Flux.<Integer>empty().collectList().block());
        System.out.println("empty collectMap = "
                + Flux.<Sale>empty()
                    .collectMap(Sale::category, Sale::amount, TreeMap::new)
                    .block());
        System.out.println("empty reduce has value = "
                + Flux.<Integer>empty().reduce(Integer::sum)
                    .blockOptional().isPresent());
        System.out.println("empty reduce(seed) = "
                + Flux.<Integer>empty().reduce(100, Integer::sum).block());
        System.out.println("empty scan = "
                + Flux.<Integer>empty().scan(Integer::sum)
                    .collectList().block());
        System.out.println("empty scan(seed) = "
                + Flux.<Integer>empty().scan(100, Integer::sum)
                    .collectList().block());
    }
}
~~~

Với **JDK 17+** và Maven, chạy trong thư mục dự án:

~~~bash
mvn -q compile exec:java
~~~

**Các dòng do chương trình in ra:**

~~~text
collectList = [10, 20, 15, 7]
collectMap = {books=15, pens=7}
reduce = 52
reduce(seed) = 152
scan = [10, 30, 45, 52]
scan(seed) = [100, 110, 130, 145, 152]
empty collectList = []
empty collectMap = {}
empty reduce has value = false
empty reduce(seed) = 100
empty scan = []
empty scan(seed) = [100]
~~~

**Tự tính lại kết quả:**

- Danh sách amounts có bốn phần tử **10, 20, 15, 7**.
- Với collectMap, **books** đến sau có số 15 thay số 10, **pens** đến sau có số 7 thay số 20. TreeMap giúp in các khóa theo thứ tự chữ cái.
- Tổng 10 + 20 + 15 + 7 = **52**; khi seed là 100, kết quả cuối **152**.
- Các tổng sau mỗi sự kiện là **10, 30, 45, 52**.
- scan seed phát cả 100 trước khi cộng, rồi 110, 130, 145, 152.
- Những dòng empty minh họa sự khác biệt giữa **container rỗng**, **Mono.empty()** và **seed**.

**Lưu ý về block():** Chương trình console dùng block() ở ranh giới để lấy kết quả đồng bộ từ một Flux hữu hạn và in ra. Trong service/controller Spring WebFlux, **trả Mono/Flux** cho framework quản lý; không chặn event loop bằng block(), blockLast(), join() hoặc get().

**Lưu ý về nhiều subscription:** Mỗi dòng trong ví dụ đăng ký lại với Flux.fromIterable(sales), một nguồn cold đọc lại List trong bộ nhớ. Nếu source là một nguồn hot hoặc một lời gọi mạng có side effect, nhiều subscription có thể làm phát sinh công việc mới hoặc nhận bộ dữ liệu khác. Khi cần nhiều thống kê trên **một lần phát dữ liệu**, phải thiết kế chia sẻ/tổng hợp một lượt thay vì mặc định gọi block nhiều lần như demo.

## 8. collectMap không tự tính tổng theo khóa

Giả sử nghiệp vụ cần tính doanh thu của từng nhóm:

~~~text
books: 10 và 15  → tổng phải là 25
pens: 20 và 7    → tổng phải là 27
~~~

**collectMap(Sale::category, Sale::amount)** không cho kết quả đó, mà cho 15 và 7 vì ghi đè khóa. Nếu muốn cộng, có thể dùng **collect(Supplier, BiConsumer)**:

~~~java
Mono<Map<String, Integer>> totals = source.collect(
        () -> new TreeMap<String, Integer>(),
        (map, sale) -> map.merge(
                sale.category(),
                sale.amount(),
                Integer::sum
        )
);
~~~

Đoạn này dùng Sale và source trong chương trình trước. Map được tạo riêng cho từng subscription, merge cộng số tiền theo khóa. Kết quả:

~~~text
{books=25, pens=27}
~~~

Đây là trường hợp **collect** tổng quát, không phải collectMap. Khi dữ liệu rất lớn, nhóm ở database hoặc tổng hợp theo cửa sổ có thể tiết kiệm dữ liệu truyền qua ứng dụng hơn.

Nếu muốn lưu toàn bộ các Sale thuộc mỗi category, dùng **collectMultimap(Sale::category)** rồi xử lý Map<K, Collection<Sale>>; cần cân nhắc chi phí bộ nhớ tương tự collectList.

## 9. Tính kết hợp, thứ tự và các phép toán dễ sai

reduce và scan tích lũy theo **thứ tự tín hiệu đến**. Với phép cộng số nguyên nhỏ, kết quả thường dễ hiểu. Nhưng không phải phép toán nào cũng cho kết quả giống nhau khi thứ tự đổi.

~~~text
Nguồn: 10, 3, 2
Phép trừ: (10 - 3) - 2 = 5

Nguồn: 3, 10, 2
Phép trừ: (3 - 10) - 2 = -9
~~~

Những điểm cần nhớ:

- **flatMap** có thể phát kết quả bất đồng bộ theo thứ tự hoàn thành, không nhất thiết theo thứ tự ban đầu.
- **collectList** giữ thứ tự onNext được quan sát, không tự phục hồi thứ tự ban đầu.
- **collectMap** giữ giá trị đến sau theo **thứ tự onNext**, không tự hiểu timestamp.
- **reduce/scan** phản ánh thứ tự dữ liệu và hàm tích lũy; với phép toán không giao hoán, thứ tự thay đổi sẽ đổi kết quả.
- Với dữ liệu tiền tệ, dùng **BigDecimal** hoặc số nguyên đơn vị nhỏ; float/double có sai số làm tròn, cộng theo thứ tự khác có thể tạo kết quả khác ở phần thập phân.
- Nếu cần bảo toàn thứ tự qua xử lý bất đồng bộ, cân nhắc **concatMap** hoặc **flatMapSequential** theo mục tiêu; cần đo độ trễ, concurrency và chi phí buffering.

Không nên suy diễn các toán tử này sẽ tự thực thi song song. Sử dụng Flux không mặc nhiên tạo thread riêng hay tăng thông lượng CPU.

## 10. Dữ liệu vô hạn, backpressure và các giới hạn thực tế

Một ví dụ nhiều người dễ dùng sai:

~~~java
Flux<Long> ticks = Flux.interval(java.time.Duration.ofSeconds(1));

// ticks.collectList() không có List cuối khi ticks chạy vô hạn.
Flux<Long> counter = ticks.scan(0L, (count, tick) -> count + 1);
// Có thể phát 0, 1, 2, 3, ... khi subscription còn hoạt động.
~~~

Nguồn ticks là chuỗi sự kiện liên tục. **collectList**, **collectMap**, **reduce** đều chờ onComplete; nếu nguồn không hoàn tất thì kết quả cuối không xuất hiện. **scan** phù hợp hơn để quan sát các giá trị trung gian, nhưng cũng không tự dừng subscription.

**Backpressure** điều tiết nhu cầu giữa Publisher và Subscriber, không bảo đảm các container tích lũy có kích thước hữu hạn. Vì vậy:

| Toán tử | Trạng thái cần giữ | Rủi ro chính |
| --- | --- | --- |
| collectList | Danh sách mọi phần tử | Bộ nhớ tăng theo số bản ghi |
| collectMap | Map các khóa/giá trị hiện có | Bộ nhớ tăng theo số khóa phân biệt |
| reduce | Một accumulator | Có thể O(1) cho sum/count; có thể tăng vô hạn nếu accumulator là List/Map |
| scan | Một accumulator và phát liên tục | State có thể lớn; tạo snapshot toàn bộ mỗi lần có thể tốn CPU/bộ nhớ |
| scan(...).collectList() | Tất cả kết quả trung gian của scan | Tích lũy trở lại thành List lớn, dù scan ban đầu cho phép streaming |

Cách giảm rủi ro:

1. **Giới hạn số phần tử** cần xử lý, tốt nhất ngay ở data source (limit, phân trang, tiêu chí lọc).
2. **Tổng hợp thay cho lưu từng phần tử** khi chỉ cần sum, count, min/max hoặc chỉ số cuối.
3. **Chia window/buffer hữu hạn** và xử lý từng đoạn khi cần thống kê theo phút, mỗi N phần tử hoặc từng trang.
4. **Giới hạn thời gian / cancellation** cho nguồn bên ngoài; có quy tắc rõ khi không có onComplete hoặc khi lỗi.
5. **Đo heap, GC, số phần tử, số khóa, độ trễ và thời gian subscription** trên tải thật.

Ví dụ nguồn hữu hạn có giới hạn:

~~~java
Mono<List<Long>> firstHundred =
        Flux.range(1, 1000)
            .take(100)
            .map(Integer::longValue)
            .collectList();
~~~

Đối với truy vấn reactive, dùng take để bảo đảm giới hạn phần tử qua pipeline nhưng vẫn cần kiểm tra kế hoạch truy vấn/tầng DB nếu performance quan trọng.

## 11. Trạng thái mutable và nhiều Subscriber

Trong Reactor, một Publisher thường có thể được subscribe nhiều lần. Nếu accumulator là **đối tượng mutable** tạo ở ngoài pipeline, các lượt subscription có thể vô tình cùng sửa một đối tượng.

Một ví dụ cần tránh về thiết kế:

~~~java
java.util.ArrayList<Integer> shared = new java.util.ArrayList<>();

Mono<java.util.ArrayList<Integer>> unsafe = Flux.just(1, 2, 3)
        .reduce(shared, (list, value) -> {
            list.add(value);
            return list;
        });
~~~

Nếu subscribe nhiều lần, shared có thể chứa dữ liệu từ những lượt trước; thậm chí có thể gặp race khi subscribe đồng thời. Không dùng cách này cho trạng thái theo request.

Dùng **collect** với Supplier cấp List mới:

~~~java
Mono<java.util.List<Integer>> isolated =
        Flux.just(1, 2, 3)
            .collect(
                    java.util.ArrayList::new,
                    java.util.List::add
            );
~~~

Hoặc dùng **reduceWith** nếu thiết kế yêu cầu accumulator được tạo lazy theo subscription:

~~~java
Mono<java.util.ArrayList<Integer>> isolatedReduce =
        Flux.just(1, 2, 3)
            .reduceWith(
                    java.util.ArrayList::new,
                    (list, value) -> {
                        list.add(value);
                        return list;
                    }
            );
~~~

Đây là các đoạn minh họa. Với scan và state mutable, còn cần chú ý **nhiều onNext có thể mang cùng tham chiếu mutable**; hãy tạo snapshot bất biến nếu downstream lưu giữ trạng thái quá khứ. Khi sử dụng Spring WebFlux, không đặt accumulator mutable vào trường singleton service để tích lũy cho các request độc lập.

## 12. Dùng trong Spring WebFlux: chọn API trả Mono hay Flux?

### API trả danh sách

~~~java
@GetMapping("/orders")
public Mono<List<OrderDto>> orders() {
    return repository.findRecentOrders()
            .map(OrderDto::from)
            .take(50)
            .collectList();
}
~~~

Thích hợp khi client muốn một mảng JSON hữu hạn. **OrderDto** và **repository** được giả định đã tồn tại; đoạn code minh họa không phải ứng dụng standalone.

### API trả tổng cuối

~~~java
@GetMapping("/orders/total")
public Mono<Long> totalCents() {
    return repository.findRecentOrders()
            .map(order -> order.amountCents())
            .reduce(0L, Long::sum);
}
~~~

Nếu nguồn rỗng thì trả 0 nhờ seed. Nếu business cần phân biệt “không có bản ghi” với “tổng bằng 0”, phải thay kiểu kết quả hoặc quy tắc empty.

### API phát tổng đang chạy theo SSE

~~~java
@GetMapping(
        value = "/orders/running-total",
        produces = org.springframework.http.MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<Long> runningTotal() {
    return repository.findRecentOrders()
            .map(order -> order.amountCents())
            .scan(0L, Long::sum);
}
~~~

scan có thể phát 0 trước khi bản ghi đầu xuất hiện. Với một repository chỉ truy vấn tập dữ liệu hữu hạn, stream kết thúc sau khi hết dữ liệu; **scan không tự tạo cập nhật realtime** khi dữ liệu DB thay đổi. Muốn realtime phải nối vào nguồn thay đổi/sự kiện phù hợp.

### API stream từng bản ghi

~~~java
@GetMapping("/orders/stream")
public Flux<OrderDto> stream() {
    return repository.findRecentOrders().map(OrderDto::from);
}
~~~

Nếu mục tiêu là stream từng bản ghi, có thể giữ Flux thay vì gom thành List. Cách HTTP client nhận dữ liệu phụ thuộc media type, codec, runtime và cách tiêu thụ; SSE cần media type phù hợp.

**Trong các controller WebFlux, trả Mono/Flux; không gọi block() để chuyển ngược về kiểu đồng bộ.**

## 13. Kiểm thử với StepVerifier và đầu vào đặc biệt

Khi dự án có **reactor-test**, có thể kiểm tra chính xác tín hiệu:

~~~java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class AggregationChecks {
    static void verify() {
        StepVerifier.create(
                Flux.just(2, 3, 5).reduce(Integer::sum)
        )
        .expectNext(10)
        .verifyComplete();

        StepVerifier.create(
                Flux.just(2, 3, 5).scan(0, Integer::sum)
        )
        .expectNext(0, 2, 5, 10)
        .verifyComplete();

        StepVerifier.create(
                Flux.<Integer>empty().reduce(Integer::sum)
        )
        .verifyComplete();
    }
}
~~~

Đây là **đoạn minh họa để đặt trong dự án test đã cài reactor-test**, không phải chương trình standalone. Các kiểm thử nên bao gồm:

- collectList giữ thứ tự onNext và phần tử trùng lặp.
- collectMap giữ giá trị **cuối theo khóa**; nếu phải giữ tất cả, kiểm tra collectMultimap.
- reduce không seed khi rỗng **không có onNext**, seed reduce có giá trị seed.
- scan không seed phát n trạng thái, scan seed phát n+1 trạng thái.
- Upstream onError: collect/reduce không phát kết quả cuối; scan có thể phát trạng thái trước lỗi.
- Nguồn không hoàn tất, cancellation và giới hạn bộ nhớ/tài nguyên.
- Nguồn bất đồng bộ đổi thứ tự phát: hợp đồng chọn “giá trị cuối” và phép tích lũy có còn đúng không.
- Nhiều subscription: trạng thái mutable có bị dùng chung ngoài ý muốn không.

Khi kiểm thử thời gian/luồng bất đồng bộ, nên sử dụng các tiện ích kiểm thử Reactor phù hợp; tránh dựa vào Thread.sleep để suy đoán thứ tự không được bảo đảm.

## 14. Những lỗi thường gặp

| Sai lầm | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| Cho rằng **collectMap** cộng các giá trị theo khóa | Giá trị đến sau ghi đè giá trị trước | Dùng collect với merge, collectMultimap, hoặc tổng hợp tại data source |
| Dùng **reduce** để cập nhật UI sau mỗi phần tử | Chỉ có một kết quả cuối sau onComplete | Dùng **scan** |
| Quên **scan(seed)** phát seed đầu tiên | Thừa một trạng thái và dễ sai n/n+1 | Xác định rõ hợp đồng UI, cân nhắc skip(1) |
| Nghĩ **reduce không seed** trên rỗng trả 0 | Mono kết thúc rỗng | Dùng reduce(0, ...) hoặc xử lý empty rõ ràng |
| Gom List/Map toàn bộ một Flux vô hạn | Không có kết quả cuối, nguy cơ tăng bộ nhớ | Giới hạn nguồn, phân trang hoặc buffer/window |
| Dựa vào thứ tự HashMap | Output không ổn định theo kỳ vọng | Dùng TreeMap/LinkedHashMap với mapSupplier khi cần |
| Chia sẻ mutable seed qua nhiều subscribers | Rò trạng thái và race | Dùng Supplier tạo state mới theo subscription |
| Dùng flatMap đồng thời rồi đòi “bản ghi cuối” theo thời gian | Kết quả phụ thuộc thứ tự onNext | Sắp xếp theo trường nghiệp vụ hoặc chọn operator đúng |
| Dùng **block()** trong request WebFlux | Chặn luồng thực thi | Trả Mono/Flux, kết hợp operator không chặn |
| Coi backpressure là giới hạn bộ nhớ cho mọi phép gom | Container vẫn có thể lớn vô hạn | Đặt giới hạn dữ liệu và đo memory/GC |

## 15. Checklist chọn toán tử

| Nhu cầu | Lựa chọn phù hợp |
| --- | --- |
| Muốn toàn bộ phần tử hữu hạn, kể cả bản ghi lặp | **collectList()** |
| Muốn một giá trị theo khóa, cho phép ghi đè khi khóa trùng | **collectMap(...)** |
| Muốn giữ mọi phần tử thuộc cùng khóa | **collectMultimap(...)** |
| Muốn tổng/count/max cuối | **reduce(...)** |
| Muốn kết quả mặc định khi không có phần tử | **reduce(seed, ...)** |
| Muốn tổng/trạng thái sau từng phần tử | **scan(...)** |
| Muốn cả trạng thái ban đầu | **scan(seed, ...)** |
| Seed phải tạo mới mỗi subscription | **reduceWith**, **scanWith**, **collect(Supplier, ...)** |
| Muốn cộng theo từng khóa | **collect** với merge, groupBy/aggregation hoặc truy vấn GROUP BY |
| Muốn xử lý lượng lớn theo lô hữu hạn | **buffer/window**, giới hạn và phân trang |
| Muốn stream dữ liệu theo thời gian | Giữ **Flux**, hoặc **scan** nếu cần trạng thái đang chạy |

## 16. Kết luận

**collectList** và **collectMap** gom Flux thành một **Mono** chứa container cuối; collectMap **ghi đè** khi trùng khóa. **reduce** tạo **một trạng thái cuối** và khác nhau giữa overload có seed và không có seed khi nguồn rỗng. **scan** tạo **một Flux các trạng thái trung gian**; scan có seed còn phát chính seed trước các trạng thái sau.

Khi chọn toán tử, hãy tự hỏi: **Nguồn có hoàn tất không? Kích thước có giới hạn không? Thứ tự có ý nghĩa không? Dữ liệu trùng khóa cần xử lý thế nào? Nguồn rỗng nên trả gì? Mỗi subscription có trạng thái riêng không?** Trong ứng dụng Spring WebFlux, trả Mono/Flux trực tiếp và giữ pipeline không chặn.

**Tài liệu chính thức:**
- [Project Reactor Flux API – collectList, collectMap, reduce, scan](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html)
- [Reactor Reference – Backpressure và request](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html)
