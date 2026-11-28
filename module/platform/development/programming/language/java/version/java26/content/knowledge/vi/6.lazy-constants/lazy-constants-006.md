# Khởi tạo nguyên tử và công bố dữ liệu an toàn giữa các luồng

Module **JAVA_VERSION_JAVA26** khảo sát các thay đổi về HTTP, pattern matching, structured concurrency, Vector API, bảo mật và hiệu năng JVM. Bài này tập trung vào một API thư viện liên quan đến khởi tạo dữ liệu dùng chung giữa nhiều luồng. Trong Java 26, **Lazy Constants** được giới thiệu dưới dạng preview API qua JEP 526. Đến JDK 27, API tiếp tục ở lần preview thứ ba theo JEP 531. Một đặc tính quan trọng của LazyConstant là khởi tạo nguyên tử: nhiều luồng có thể cùng gọi get(), nhưng chỉ một luồng chạy hàm tính giá trị; các luồng còn lại chờ kết quả. Việc khởi tạo có quan hệ happens-before với lần đọc nội dung đã khởi tạo, nhờ đó đối tượng được công bố an toàn cho các luồng nhận giá trị.

Bài này thuộc module **JAVA_VERSION_JAVA26**, nên cần hiểu đúng API ở Java 26 và cách nó tiếp tục thay đổi ở JDK 27. Tại ngày 27-11-2026, JDK 27 là bản phát hành hiện hành; LazyConstant vẫn là preview API, chưa phải API Java SE ổn định. Ví dụ chính dùng JDK 27 để phản ánh hợp đồng API mới nhất. Không đưa API preview vào thư viện hoặc giao diện công khai cần tương thích lâu dài.

## 1. Trạng thái và phiên bản API

| Release | JEP | Tên và trạng thái |
|---|---|---|
| Java 25 | JEP 502 | Stable Values, preview lần đầu; API khi đó mang tên StableValue |
| Java 26 | JEP 526 | Lazy Constants, preview lần thứ hai |
| Java 27 | JEP 531 | Lazy Constants, preview lần thứ ba; vẫn là preview API |

JDK 27 phát hành ngày 15-09-2026. Tài liệu Java SE 27 đánh dấu **java.lang.LazyConstant** là preview API. Vì vậy, để biên dịch và chạy mã sử dụng API này, phải bật preview ở cả compiler và JVM bằng JDK 27.

Có một khác biệt quan trọng giữa hai release:

- API Java 26 có các phương thức **isInitialized()** và **orElse(...)**. Tài liệu API Java 26 cũng quy định nếu hàm tính giá trị ném exception, exception được chuyển tiếp cho caller và lazy constant vẫn chưa khởi tạo; lần gọi get() sau có thể thử tính lại.
- API Java 27 chỉ công bố các phương thức **of(...)**, **get()**, **equals(...)**, **hashCode()** và **toString()**. Không dựa vào isInitialized() hoặc orElse() trong mã nhắm JDK 27.
- Trong Java 27, nếu hàm tính giá trị ném unchecked exception hoặc trả về null, lazy constant chuyển sang trạng thái lỗi. Lần get() đầu tiên ném NoSuchElementException có cause; các lần get() tiếp theo cũng ném NoSuchElementException nhưng không chạy lại hàm tính giá trị.

Do đó, không sao chép nguyên ví dụ LazyConstant của Java 26 sang JDK 27 mà không kiểm tra API và hành vi lỗi. Các ví dụ trong bài dùng phần API chung giữa hai release, đồng thời giải thích rõ khác biệt về xử lý lỗi.

## 2. LazyConstant bảo đảm điều gì?

LazyConstant là một holder chứa một giá trị được tính khi cần. Tạo LazyConstant chưa tính nội dung. Lần đầu gọi **get()**, hàm Supplier được truyền cho **LazyConstant.of(...)** sẽ tính giá trị. Khi khởi tạo thành công, nội dung không thể bị thay thế; các lần get() sau trả về cùng nội dung đó.

Có ba bảo đảm cốt lõi:

1. **Khởi tạo tối đa một lần:** với cùng một LazyConstant instance, chỉ một luồng được chọn để chạy Supplier, kể cả khi nhiều luồng đồng thời gọi get().
2. **Công bố an toàn:** thao tác chạy Supplier và khởi tạo nội dung xảy ra trước lần đọc nội dung đã khởi tạo theo quan hệ happens-before. Các luồng nhận được giá trị sẽ thấy trạng thái được thiết lập trong quá trình tạo đối tượng, bao gồm các field final của đối tượng mới.
3. **Giá trị không đổi sau khi khởi tạo:** holder không cho thay thế nội dung bằng giá trị khác. Tính bất biến này cho phép JVM có cơ hội tối ưu như constant folding, tương tự một số tối ưu dành cho field final.

Hàm Supplier chạy trên chính luồng caller đã thắng cuộc đua khởi tạo; LazyConstant không tạo một worker thread riêng. Các luồng khác gọi get() trong lúc khởi tạo sẽ bị chặn cho đến khi có kết quả hoặc quá trình tính giá trị thất bại. Vì thế, việc khởi tạo có thể làm tăng độ trễ của request đầu tiên nếu request đó là caller đầu tiên.

## 3. Phân biệt khởi tạo nguyên tử và công bố an toàn

Hai khái niệm này liên quan chặt chẽ nhưng trả lời hai câu hỏi khác nhau.

**Khởi tạo nguyên tử** trả lời: trong cuộc đua giữa nhiều luồng, có bao nhiêu luồng thực sự chạy hàm tạo giá trị? Với một LazyConstant, chỉ một luồng chạy Supplier. Các luồng khác không tạo thêm bản sao cạnh tranh.

**Công bố an toàn** trả lời: khi một luồng nhận được tham chiếu đến đối tượng vừa tạo, nó có nhìn thấy đầy đủ trạng thái đã thiết lập trong quá trình tạo hay không? Quan hệ happens-before bảo đảm việc khởi tạo nội dung xảy ra trước khi nội dung được đọc. Vì vậy, các field final được thiết lập trong constructor được công bố an toàn cùng đối tượng.

Ví dụ, nếu Supplier tạo một record cấu hình có endpoint và timeout, các luồng gọi get() sẽ nhận cùng record đã được khởi tạo hoàn chỉnh. Chúng không quan sát một nửa constructor hoặc một tham chiếu chưa được công bố đúng cách.

Điều này không biến mọi đối tượng được chứa thành bất biến sâu. LazyConstant bảo đảm tham chiếu nội dung không bị thay thế; đối tượng mà tham chiếu trỏ tới vẫn có thể là mutable, ví dụ ArrayList. Nếu một luồng sửa danh sách sau khi khởi tạo trong khi luồng khác đọc, ứng dụng vẫn phải dùng cơ chế đồng bộ thích hợp cho các thao tác đó.

## 4. Ví dụ nhiều luồng cùng khởi tạo một cấu hình

Ví dụ sau tạo một LazyConstant chứa cấu hình ứng dụng. Tám luồng cùng chờ một tín hiệu bắt đầu rồi gọi get() gần như đồng thời. AtomicInteger chỉ dùng để đếm số lần Supplier được thực thi trong bài thực hành.

    import java.lang.LazyConstant;
    import java.util.ArrayList;
    import java.util.List;
    import java.util.concurrent.CountDownLatch;
    import java.util.concurrent.ExecutorService;
    import java.util.concurrent.Executors;
    import java.util.concurrent.Future;
    import java.util.concurrent.atomic.AtomicInteger;

    public class LazyPublicationDemo {

        record AppConfig(
                String endpoint,
                int timeoutMillis,
                List<String> regions) {
        }

        private static final AtomicInteger COMPUTE_COUNT =
                new AtomicInteger();

        private static final LazyConstant<AppConfig> CONFIG =
                LazyConstant.of(() -> {
                    COMPUTE_COUNT.incrementAndGet();

                    return new AppConfig(
                            "https://api.example.test",
                            2500,
                            List.of("ap-southeast-1", "ap-southeast-2")
                    );
                });

        public static void main(String[] args) throws Exception {
            int workerCount = 8;

            CountDownLatch ready = new CountDownLatch(workerCount);
            CountDownLatch start = new CountDownLatch(1);

            try (ExecutorService pool =
                         Executors.newFixedThreadPool(workerCount)) {

                List<Future<AppConfig>> results = new ArrayList<>();

                for (int i = 0; i < workerCount; i++) {
                    results.add(pool.submit(() -> {
                        ready.countDown();
                        start.await();
                        return CONFIG.get();
                    }));
                }

                ready.await();
                start.countDown();

                AppConfig first = results.get(0).get();
                boolean sameInstance = true;

                for (Future<AppConfig> result : results) {
                    sameInstance &= result.get() == first;
                }

                System.out.println(
                        "Supplier executions: " + COMPUTE_COUNT.get()
                );
                System.out.println(
                        "All threads got same instance: " + sameInstance
                );
                System.out.println(
                        "Endpoint: " + first.endpoint()
                );
                System.out.println(
                        "Regions: " + first.regions()
                );
            }
        }
    }

Biên dịch và chạy bằng JDK 27:

    javac --enable-preview --release 27 -encoding UTF-8 -d out src/LazyPublicationDemo.java
    java --enable-preview -cp out LazyPublicationDemo

Kết quả mong đợi về mặt logic:

    Supplier executions: 1
    All threads got same instance: true
    Endpoint: https://api.example.test
    Regions: [ap-southeast-1, ap-southeast-2]

Thứ tự các luồng hoàn tất không cố định, nhưng Supplier của CONFIG chỉ được chạy một lần. Mỗi Future nhận cùng một tham chiếu AppConfig. Record có các thành phần final; danh sách vùng được tạo bằng List.of nên không thể sửa qua tham chiếu trả về.

Nếu thay CONFIG bằng nhiều LazyConstant instance khác nhau, mỗi instance có vòng đời khởi tạo riêng. Bảo đảm at-most-once áp dụng cho từng instance, không phải cho mọi Supplier có cùng mã nguồn hoặc mọi instance của cùng một lớp.

## 5. Happens-before và giới hạn của bảo đảm bộ nhớ

Tài liệu Java SE 27 mô tả rõ: việc gọi computing function và việc khởi tạo nội dung lazy constant xảy ra trước (happens-before) việc đọc nội dung đã khởi tạo. Đây là cơ sở để công bố an toàn đối tượng cho các luồng cạnh tranh.

Có thể hình dung trình tự như sau:

    Thread A                         Thread B
    --------                         --------
    gọi CONFIG.get()
    chạy Supplier
    tạo AppConfig
    hoàn tất khởi tạo
          |                              |
          |  happens-before              |
          +----------------------------->|
                                      get() nhận nội dung
                                      đọc các field đã tạo

Các luồng chờ không cần tự tạo thêm một khóa quanh lời gọi get() để bảo vệ bước khởi tạo của LazyConstant. Cơ chế đồng bộ thuộc implementation của LazyConstant.

Tuy nhiên, API cũng cảnh báo rằng những lần đọc sau có thể được JVM loại bỏ nhờ constant folding. Vì vậy, không có thêm bảo đảm ordering hoặc visibility nào cho các lần gọi get() sau chỉ vì chúng được gọi lại. Đặc biệt:

- Không dùng get() như một hàng rào bộ nhớ cho các thay đổi xảy ra sau khi đối tượng đã khởi tạo.
- Không sửa các field mutable sau khi công bố rồi kỳ vọng lần get() kế tiếp tự công bố thay đổi đó cho luồng khác.
- Nếu nội dung chứa đối tượng mutable, hãy dùng synchronized, volatile, lock, atomic hoặc cấu trúc dữ liệu đồng thời phù hợp cho các lần cập nhật và đọc sau này.
- Ưu tiên record, field final, collection bất biến và đối tượng cấu hình không thay đổi sau khi tạo.

LazyConstant giải quyết việc tạo và công bố một giá trị một lần. Nó không thay thế toàn bộ Java Memory Model và không phải một cơ chế đồng bộ tổng quát.

## 6. Supplier chạy trên caller thread và các luồng chờ

Luồng đầu tiên gọi get() khi constant chưa được khởi tạo sẽ chạy Supplier. Nếu Supplier đọc file cấu hình, phân tích dữ liệu lớn hoặc tạo một client phức tạp, thời gian xử lý đó được tính vào luồng caller.

Các luồng cạnh tranh gọi get() trong thời gian này sẽ bị chặn. API không cung cấp timeout hoặc cơ chế hủy việc khởi tạo. Nếu Supplier bị block vô hạn, các luồng đang chờ cùng LazyConstant cũng có thể bị block vô hạn.

Ngắt luồng không hủy quá trình khởi tạo. Nếu computing thread bị interrupt, LazyConstant không xóa trạng thái interrupt của luồng và get() không ném InterruptedException. Supplier vẫn cần tự xác định cách xử lý interruption nếu công việc bên trong có thể bị ngắt.

Vì vậy, Supplier nên thực hiện một lần khởi tạo có giới hạn và có thể dự đoán. Không nên đặt một thao tác mạng không timeout hoặc một công việc chờ vô hạn vào Supplier. Nếu ứng dụng cần tránh độ trễ ở request đầu tiên, có thể chủ động gọi get() trong giai đoạn khởi động có kiểm soát để khởi tạo trước.

## 7. Xử lý lỗi khởi tạo trong JDK 27

Đây là điểm cần chú ý khi chuyển từ JDK 26 sang JDK 27.

Trong JDK 27, nếu Supplier ném unchecked exception (RuntimeException hoặc Error), LazyConstant chuyển sang trạng thái lỗi. Lần get() đầu tiên ném **NoSuchElementException** với exception gốc làm cause. Các lần get() tiếp theo cũng ném NoSuchElementException, nhưng không chạy lại Supplier và không còn cause gốc trong exception mới.

Nếu Supplier trả về null, LazyConstant không thể lưu null. Lần get() đầu tiên ném NoSuchElementException có NullPointerException làm cause. Muốn biểu diễn một giá trị có thể vắng mặt, hãy dùng Optional làm nội dung:

    static final LazyConstant<Optional<String>> OPTIONAL_NAME =
            LazyConstant.of(() -> Optional.empty());

Nếu Supplier gọi đệ quy lại chính LazyConstant đang được khởi tạo, JDK 27 báo NoSuchElementException với IllegalStateException làm cause. Tránh tạo vòng phụ thuộc giữa các lazy constant; thiết kế dependency graph theo một chiều để không có chu trình.

| Tình huống trên JDK 27 | Kết quả |
|---|---|
| Supplier trả về một object khác null | Nội dung được khởi tạo và giữ nguyên |
| Supplier ném RuntimeException hoặc Error | Trạng thái lỗi; get() đầu tiên ném NoSuchElementException có cause |
| Gọi get() sau khi đã ở trạng thái lỗi | NoSuchElementException; Supplier không được chạy lại |
| Supplier trả về null | NoSuchElementException có NullPointerException làm cause |
| Supplier gọi đệ quy LazyConstant đang khởi tạo | NoSuchElementException có IllegalStateException làm cause |

Trong JDK 26 second preview, hợp đồng API có khác: nếu Supplier ném throwable, throwable được chuyển tiếp cho caller và lazy constant vẫn chưa khởi tạo; lần gọi get() sau có thể thử lại. JDK 26 cũng mô tả null bằng NullPointerException và đệ quy bằng IllegalStateException. Không áp dụng kỳ vọng retry của JDK 26 cho JDK 27.

Điều này có ảnh hưởng trực tiếp đến thiết kế Supplier. Nếu việc tạo cấu hình hoặc tài nguyên có thể thất bại tạm thời, không nên mặc định rằng LazyConstant sẽ tự thử lại. Hãy quyết định chính sách retry ở tầng ứng dụng trước khi chuyển lỗi thành unchecked exception, hoặc tạo một cơ chế phục hồi riêng phù hợp với vòng đời tài nguyên.

## 8. Kết hợp các lazy constant có phụ thuộc

Một LazyConstant có thể phụ thuộc vào LazyConstant khác. Ví dụ, một service cần cấu hình trước khi tạo:

    record DatabaseConfig(String url, String username) {
    }

    final class DatabaseClient {
        private final DatabaseConfig config;

        DatabaseClient(DatabaseConfig config) {
            this.config = config;
        }

        String endpoint() {
            return config.url();
        }
    }

    final class Services {
        static final LazyConstant<DatabaseConfig> DATABASE_CONFIG =
                LazyConstant.of(() ->
                        new DatabaseConfig(
                                "jdbc:postgresql://db.example.test/app",
                                "app_user"
                        )
                );

        static final LazyConstant<DatabaseClient> DATABASE_CLIENT =
                LazyConstant.of(() ->
                        new DatabaseClient(DATABASE_CONFIG.get())
                );

        static DatabaseClient database() {
            return DATABASE_CLIENT.get();
        }
    }

Lần đầu gọi Services.database(), DATABASE_CLIENT bắt đầu khởi tạo. Supplier của nó gọi DATABASE_CONFIG.get(), nên cấu hình database được tạo trước; sau đó DatabaseClient mới được tạo và công bố. Những lần truy cập sau dùng lại các nội dung đã khởi tạo.

Mô hình này phù hợp với đồ thị phụ thuộc một chiều: cấu hình nền tảng được tạo trước, service phụ thuộc được tạo sau. Tránh chu trình như A cần B trong constructor còn B lại gọi A.get(). Đệ quy hoặc phụ thuộc vòng có thể đưa constant vào trạng thái lỗi và khiến các lần truy cập sau tiếp tục thất bại.

Nếu nhiều service dùng chung một cấu hình, hãy chia sẻ đúng một LazyConstant cấu hình. Nếu tạo hai LazyConstant riêng cùng chạy một Supplier, chúng là hai holder khác nhau và có thể tạo hai đối tượng.

## 9. LazyConstant và tối ưu hóa JVM

Nội dung của LazyConstant không thay đổi sau khi khởi tạo thành công. JVM có thể xem nội dung này như một giá trị hằng và thực hiện **constant folding**, nghĩa là loại bỏ một số lần đọc tham chiếu và dùng giá trị đã quan sát trước đó.

Tối ưu này có điều kiện. Tài liệu Java SE 27 mô tả trường hợp tham chiếu trực tiếp từ field **static final** đến LazyConstant, hoặc một chuỗi field đáng tin cậy đi từ static final đến LazyConstant. Các field đáng tin cậy có thể gồm static final, record fields và final instance fields trong hidden classes.

Ví dụ CONFIG trong bài được khai báo static final, nên cấu trúc tham chiếu có thể đủ điều kiện để JVM áp dụng tối ưu. Tuy nhiên, API chỉ cho phép JVM tối ưu; không bảo đảm mọi runtime, mọi lần chạy hoặc mọi cách truy cập đều được constant-fold. Hãy đo bằng benchmark phù hợp nếu hiệu năng là lý do chính để áp dụng.

LazyConstant còn giữ tham chiếu mạnh đến nội dung sau khi khởi tạo. Nội dung không thể được xóa khỏi holder; nếu LazyConstant còn reachable thì object bên trong cũng còn reachable. Do đó, không dùng nó cho cache cần eviction, dữ liệu phải refresh, phiên làm việc ngắn hạn hoặc tài nguyên cần đóng và giải phóng theo thời điểm.

LazyConstant không làm cho object bên trong tự trở thành immutable. Nếu holder chứa ArrayList, mảng hoặc object có state thay đổi, các thành phần đó vẫn cần chính sách quản lý riêng. Tài liệu API cũng lưu ý LazyConstant không Serializable và implementation được phép đồng bộ trên chính instance LazyConstant; không dùng synchronized(lazyConstant) làm giao thức khóa của ứng dụng.

## 10. Biên dịch và chạy preview đúng phiên bản

LazyConstant là preview API trong cả JDK 26 và JDK 27. API nằm trong module **java.base**, nên không cần thêm module bằng --add-modules.

Với JDK 27, dùng cùng release cho compiler và runtime:

    javac --enable-preview --release 27 -encoding UTF-8 -d out src/LazyPublicationDemo.java
    java --enable-preview -cp out LazyPublicationDemo

Với JDK 26 second preview, phải dùng compiler và runtime JDK 26:

    javac --enable-preview --release 26 -encoding UTF-8 -d out src/LazyPublicationDemo.java
    java --enable-preview -cp out LazyPublicationDemo

Không dùng javac JDK 27 với --release 26 rồi kỳ vọng bật preview của JDK 26; preview chỉ được bật cho release hiện tại của compiler. Class file phụ thuộc preview của một release cũng phải chạy với JVM cùng release và có --enable-preview.

Trong IDE hoặc build tool, kiểm tra riêng JDK của project, compiler toolchain, test worker và application runner. Chỉ cấu hình compiler preview là chưa đủ nếu JVM chạy test không bật preview. Khi đổi từ JDK 26 sang JDK 27, hãy biên dịch lại toàn bộ class file phụ thuộc preview và kiểm tra khác biệt API đã nêu ở phần đầu.

## 11. Khi nào nên dùng và khi nào nên chọn cách khác?

LazyConstant phù hợp khi cần một giá trị:

- Được tính lần đầu khi thật sự cần.
- Chỉ được khởi tạo một lần cho một holder.
- Không thay đổi sau khi tạo.
- Có thể được chia sẻ cho nhiều luồng sau khi khởi tạo.
- Có chi phí tạo đủ đáng kể để muốn trì hoãn, nhưng không cần refresh hoặc eviction.

Ví dụ phù hợp gồm metadata bất biến, cấu hình đã phân tích, registry chỉ đọc, logger hoặc service dùng chung có vòng đời ứng dụng.

Không nên dùng LazyConstant cho:

- Cache cần xóa hoặc thay thế nội dung.
- Token, credential hoặc cấu hình cần xoay vòng định kỳ.
- Trạng thái request/session thay đổi liên tục.
- Đối tượng có vòng đời cần đóng tài nguyên và giải phóng chủ động.
- Tác vụ khởi tạo có thể block vô hạn hoặc cần timeout/cancellation.
- Dữ liệu mutable cần đồng bộ nhiều lần sau khi công bố.

Nếu dữ liệu phải thay đổi, hãy dùng một mô hình state có thể cập nhật và đồng bộ rõ ràng, chẳng hạn AtomicReference hoặc cấu trúc đồng thời phù hợp. Nếu chỉ cần một giá trị được tạo khi class được khởi tạo và không cần trì hoãn, field static final hoặc instance final thông thường vẫn là lựa chọn đơn giản.

## 12. Checklist kiểm chứng an toàn đa luồng

1. Xác nhận đúng JDK và trạng thái preview của LazyConstant trong release đang dùng.
2. Tạo đúng một LazyConstant instance cho giá trị cần chia sẻ.
3. Giữ holder trong field final hoặc static final có vòng đời phù hợp.
4. Supplier tạo xong toàn bộ trạng thái đối tượng trước khi trả về.
5. Không để đối tượng thoát ra ngoài trong lúc constructor hoặc Supplier vẫn đang thiết lập nó.
6. Dùng nhiều luồng cùng gọi get() và xác nhận Supplier chỉ chạy một lần.
7. Kiểm tra các field final và dữ liệu cấu hình sau khi nhận giá trị từ get().
8. Không dựa vào lần get() tiếp theo để công bố các thay đổi mutable xảy ra sau khởi tạo.
9. Xác định chính sách lỗi: trên JDK 27, unchecked exception/null đưa constant vào trạng thái lỗi và không tự retry.
10. Tránh dependency cycle, Supplier block vô hạn và giữ tài nguyên lâu hơn vòng đời mong muốn.
11. Bật --enable-preview ở cả compiler và runtime cùng JDK release.
12. Đo hiệu năng thực tế trước khi kết luận constant folding tạo ra cải thiện đáng kể.

## Tài liệu chính thức

- [Java SE 27 API — LazyConstant](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/LazyConstant.html): hợp đồng API hiện hành, xử lý lỗi, khởi tạo nguyên tử, happens-before, safe publication và constant folding.
- [Oracle — Lazy Constants, Java SE 27 Core Libraries](https://docs.oracle.com/en/java/javase/27/core/lazy-constants.html): hướng dẫn sử dụng LazyConstant, composition và ví dụ khởi tạo theo nhu cầu.
- [Oracle — JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): xác nhận Lazy Constants là preview lần thứ ba theo JEP 531.
- [Oracle — Significant Changes in JDK 27](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html): tổng quan các thay đổi của JDK 27.
- [Java SE 26 API — LazyConstant](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/LazyConstant.html): đối chiếu preview lần thứ hai, các phương thức và semantics lỗi của JDK 26.
- [Oracle — JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html): xác nhận Lazy Constants là preview lần thứ hai theo JEP 526.

Tại ngày 27-11-2026, LazyConstant vẫn là preview API trong JDK 27. Bảo đảm khởi tạo nguyên tử và công bố an toàn là phần cốt lõi của hợp đồng API; nhưng preview có thể thay đổi hoặc bị loại khỏi release tương lai. Chỉ dùng để thực hành hoặc thử nghiệm có kiểm soát cho đến khi API trở thành final và dự án xác nhận lại tương thích.
