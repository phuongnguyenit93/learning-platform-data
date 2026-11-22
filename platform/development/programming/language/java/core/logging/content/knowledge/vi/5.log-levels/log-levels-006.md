# OFF và ALL trong Java Core Logging

## 1. Mục tiêu học tập

Trong hệ thống logging, **OFF** và **ALL** là hai giá trị đặc biệt nằm ở hai đầu của thang mức log. Chúng thường được sử dụng làm **ngưỡng cấu hình**: OFF để không nhận sự kiện logging thông thường; ALL để không loại sự kiện chỉ vì mức độ ưu tiên. Hiểu đúng hai giá trị này rất quan trọng khi bạn cần giảm log ồn, điều tra sự cố hoặc chẩn đoán vì sao một bản ghi không xuất hiện.

Sau bài học, bạn có thể:

- Phân biệt **mức độ của sự kiện** (INFO, WARNING, FINE…) với **ngưỡng lọc** được đặt cho Logger hoặc Handler.
- Giải thích chính xác ý nghĩa của **java.util.logging.Level.OFF** và **Level.ALL** trong Java Util Logging (JUL).
- Hiểu cách Level, Filter, Handler và Logger cha/con kết hợp để quyết định bản ghi có xuất ra hay không.
- Sử dụng OFF và ALL trong code Java 17+ và cấu hình **logging.properties**.
- Nhận diện các tình huống OFF không vô hiệu hóa mọi logger con và ALL không khiến mọi bản ghi tự động được in.
- Chọn cấu hình an toàn khi vận hành ứng dụng, tránh mất thông tin điều tra hoặc sinh ra quá nhiều log.

**Phạm vi:** Bài này tập trung vào **log level** của Java Core Logging, sử dụng JUL làm ví dụ chạy độc lập. Các framework như Logback và Log4j 2 có khái niệm tương tự nhưng có API/cấu hình và đường xử lý riêng.

## 2. Ngưỡng logging khác mức độ của một sự kiện

Một ứng dụng thường phát các bản ghi với mức độ như SEVERE, WARNING, INFO, FINE và FINEST. Khi phát bản ghi, Logger so sánh level của sự kiện với **mức ngưỡng hiệu lực** (effective level) của Logger.

Với các level chuẩn của JUL, thứ tự từ ngưỡng cao xuống thấp là:

| Level của JUL | Giá trị số (intValue) | Cách hiểu thông thường |
| --- | ---: | --- |
| **OFF** | 2.147.483.647 | Tắt nhận log ở ngưỡng này; giá trị điều khiển đặc biệt |
| **SEVERE** | 1.000 | Sự cố nghiêm trọng |
| **WARNING** | 900 | Điều kiện bất thường cần chú ý |
| **INFO** | 800 | Thông tin vận hành |
| **CONFIG** | 700 | Thông tin cấu hình |
| **FINE** | 500 | Chi tiết gỡ lỗi |
| **FINER** | 400 | Chi tiết hơn |
| **FINEST** | 300 | Mức chi tiết rất cao |
| **ALL** | -2.147.483.648 | Cho phép toàn bộ level tại điểm kiểm tra ngưỡng; giá trị điều khiển đặc biệt |

**Điểm cốt lõi:** **OFF** và **ALL** khác các severity như WARNING hoặc INFO. Chúng chủ yếu mang ý nghĩa **điều khiển mức được chấp nhận**, không phải loại sự kiện nghiệp vụ mà bạn nên gắn cho một dòng log. Trong code, hãy tạo event ở INFO, WARNING, SEVERE, FINE… và dùng OFF/ALL cho cấu hình.

Có thể hình dung một ngưỡng như cánh cửa:

~~~text
Level của record:  SEVERE > WARNING > INFO > CONFIG > FINE > FINER > FINEST

Ngưỡng INFO:       nhận SEVERE, WARNING, INFO; loại CONFIG, FINE, FINER, FINEST
Ngưỡng FINE:       nhận SEVERE ... FINE; loại FINER và FINEST
Ngưỡng ALL:        không loại record chuẩn chỉ vì level quá thấp
Ngưỡng OFF:        chặn record logging thông thường tại điểm đó
~~~

Thang giá trị số giúp JUL so sánh ngưỡng. **Tuy nhiên, không nên lấy phép so sánh số tự viết rồi giả định nó thay thế trọn vẹn thuật toán logging**: Logger, Handler và Filter còn có hợp đồng riêng, trong đó OFF được xử lý như một mức tắt đặc biệt. Ví dụ, gọi **logger.log(Level.OFF, "message")** không phải cách phát sự kiện chuẩn và có thể tạo hành vi khó hiểu. Hãy tránh dùng OFF hoặc ALL làm severity của event.

## 3. Level.OFF: tắt logging tại một điểm kiểm tra

**Level.OFF** nghĩa là **vô hiệu hóa việc chấp nhận các sự kiện log thông thường** ở Logger/Handler được cấu hình mức đó.

Ví dụ:

~~~java
import java.util.logging.Level;
import java.util.logging.Logger;

Logger logger = Logger.getLogger("demo.service");
logger.setLevel(Level.OFF);

logger.info("Starting service");
logger.warning("Fallback activated");
logger.severe("Database unavailable");
~~~

Đây là **đoạn mã minh họa**, không phải chương trình Java độc lập vì không có lớp và phương thức main. Sau khi Logger được đặt OFF, những lời gọi thông thường ở INFO, WARNING và SEVERE không được Logger này chấp nhận. Ngay cả SEVERE cũng bị chặn: OFF không có nghĩa “chỉ tắt DEBUG”.

Các điểm cần lưu ý:

1. **OFF áp dụng tại Logger được cấu hình**, và có thể ảnh hưởng tới Logger con **kế thừa** mức đó.
2. Nếu một Logger con **có level riêng**, nó có thể chấp nhận bản ghi dù Logger cha đang ở OFF. Không được coi OFF của một parent là công tắc toàn cục cho mọi descendant.
3. **Handler cũng có level riêng**. Một Handler đặt OFF sẽ không xuất các record logging thông thường ngay cả khi Logger đã cho chúng đi qua.
4. **OFF không xóa log đã ghi**, không xóa file và không chặn nguồn telemetry khác như metrics/traces hoặc các logger không nằm trong phạm vi cấu hình.
5. Nếu muốn tắt hoàn toàn logging của **một thành phần**, phải xác định đúng những logger, handler, thư viện và pipeline thực sự phát/nhận sự kiện của thành phần đó.
6. Tắt log bằng OFF có thể khiến bạn mất manh mối khi điều tra lỗi. Dùng có mục đích, có phạm vi và có cách khôi phục.

### 3.1. OFF không đồng nghĩa với mức lỗi cao nhất

Một suy luận sai là “OFF nằm phía trên SEVERE, nên chỉ log cực kỳ nghiêm trọng mới được ghi”. Với JUL, **OFF biểu thị tắt**, không phải một ngưỡng lỗi “cao hơn SEVERE” để ứng dụng tiếp tục chọn sự kiện nghiêm trọng hơn. Trong vận hành, **không có level sự kiện chuẩn nào cao hơn SEVERE mà bạn nên dùng để vượt OFF**.

Nếu yêu cầu là “chỉ ghi lỗi nghiêm trọng”, hãy đặt **Level.SEVERE**, không đặt OFF:

~~~java
logger.setLevel(Level.SEVERE);
logger.severe("Unrecoverable task failure"); // Được Logger chấp nhận.
logger.warning("Retrying");                   // Bị Logger loại.
~~~

Tình huống nào dùng OFF? Ví dụ bạn đang chạy một thao tác có giới hạn và muốn tạm ngưng một logger thử nghiệm gây quá nhiều log không hữu ích; sau đó khôi phục level theo cấu hình chuẩn.

## 4. Level.ALL: cho Logger hoặc Handler nhận mọi mức

**Level.ALL** nghĩa là tại **điểm kiểm tra level được đặt ALL**, các mức sự kiện thông thường đều đủ điều kiện đi tiếp:

~~~java
Logger logger = Logger.getLogger("demo.service");
logger.setLevel(Level.ALL);

logger.severe("Service failed");
logger.info("Service started");
logger.fine("Query arguments prepared");
logger.finest("Low-level tracing detail");
~~~

Nhưng **ALL không có nghĩa tất cả các dòng trên chắc chắn được in ra console hoặc file**. Nó chỉ gỡ ngưỡng lọc theo level của Logger đó. Bản ghi còn phải qua những bước khác: Logger Filter nếu có, Handler tương ứng, Handler level, Handler Filter, formatter, sink và hệ thống thu thập.

Ví dụ nếu Logger ở ALL nhưng ConsoleHandler vẫn ở INFO, các bản ghi **FINE** và **FINEST** sẽ bị Handler loại. Đây là tình huống rất phổ biến khi lập trình viên “bật ALL rồi mà không thấy debug”.

### 4.1. ALL không đồng nghĩa với ghi không giới hạn tài nguyên

ALL là mức cấu hình, **không phải chính sách đảm bảo nhận đủ mọi bản ghi** trong toàn hệ thống. Những yếu tố khác có thể khiến bản ghi không đến đích:

- Filter loại theo nội dung hoặc thuộc tính.
- Handler không được gắn vào Logger hoặc Logger không chuyển record tới parent handler.
- Handler level cao hơn level record.
- Queue/async appender đầy, collector bị lỗi, exporter mất kết nối.
- Backend áp dụng sampling, rate limit hoặc retention.
- Code không hề gọi logging tại nhánh xử lý đang xét.

Bật ALL trên phạm vi rộng, đặc biệt ở thư viện nhiều sự kiện hoặc trong vòng lặp lớn, có thể tạo **khối lượng log lớn**, ảnh hưởng I/O, CPU, dung lượng lưu trữ, độ trễ và chi phí truy vấn. Khi chỉ cần chi tiết ở một package, chọn Logger/package đó và bật trong thời gian cần điều tra.

## 5. Tác động của Logger và Handler: phải qua cả hai lớp

JUL thường có ít nhất hai mức ngưỡng quan trọng:

- **Logger level:** lọc trước khi sự kiện được gửi đến các Handler.
- **Handler level:** lọc trên từng đích xuất. Một Logger có thể gửi tới nhiều Handler, và mỗi Handler có chính sách riêng.

Bảng sau giả định dùng các record ở mức tiêu chuẩn, không có Filter bổ sung và record thực sự được chuyển tới Handler:

| Logger level | Handler level | Record INFO | Record FINE | Record SEVERE | Kết luận |
| --- | --- | --- | --- | --- | --- |
| **OFF** | ALL | Không | Không | Không | Logger chặn |
| **ALL** | INFO | Có | Không | Có | Handler chặn FINE |
| **ALL** | ALL | Có | Có | Có | Không bị chặn bởi level |
| **INFO** | ALL | Có | Không | Có | Logger chặn FINE |
| **ALL** | OFF | Không | Không | Không | Handler chặn |
| **WARNING** | FINE | Không | Không | Có | Logger quyết định ngưỡng cao hơn |
| **FINE** | WARNING | Không | Không | Có | Handler quyết định ngưỡng cao hơn |

Trong những trường hợp không có filter, mức thực sự xuất ra thường phải **vượt qua cả hai ngưỡng**. Nhưng không nên cố tạo một “effective level” chung cho toàn ứng dụng: với nhiều Handler, mỗi đích có ngưỡng và filter riêng.

Luồng xử lý minh họa:

~~~text
Code gọi logger.fine("query.detail")
      |
      v
Logger: level = ALL?
  | yes
  v
Logger Filter có cho phép?
  | yes
  v
Handler A (console): level = INFO  -> FINE bị chặn
Handler B (file):    level = ALL   -> FINE được ghi nếu Filter của B cho phép
~~~

Đây là lý do một event có thể xuất hiện trong file mà không xuất trên console, hoặc ngược lại.

## 6. Ví dụ Java 17+ độc lập: kiểm chứng OFF, ALL và kế thừa

Chương trình dưới đây chỉ sử dụng **java.util.logging** trong JDK. Nó tạo một Handler in ra **stdout** với một formatter đơn giản ngay trong phương thức publish để nhìn rõ các record được chấp nhận. Handler tự gọi **isLoggable(record)** để tôn trọng level/filter đã cấu hình.

Tạo tệp **OffAllLevelsDemo.java**:

~~~java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class OffAllLevelsDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger("lesson.off.all");
        logger.setUseParentHandlers(false);

        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getLevel().getName() + " | " + record.getMessage());
                }
            }

            @Override public void flush() {}
            @Override public void close() {}
        };
        handler.setLevel(Level.INFO);
        logger.addHandler(handler);

        try {
            logger.setLevel(Level.OFF);
            logger.severe("off.severe");
            System.out.println("logger OFF: " + logger.isLoggable(Level.SEVERE));

            logger.setLevel(Level.ALL);
            logger.fine("all.fine");
            logger.info("all.info");

            handler.setLevel(Level.ALL);
            logger.finest("all.finest");

            logger.setLevel(Level.WARNING);
            logger.info("warning.info");
            logger.warning("warning.warning");

            handler.setLevel(Level.OFF);
            logger.severe("handler.off.severe");
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }

        Logger parent = Logger.getLogger("lesson.parent");
        parent.setLevel(Level.OFF);
        Logger child = Logger.getLogger("lesson.parent.child");
        child.setLevel(null);
        System.out.println("child inherits OFF: " + child.isLoggable(Level.INFO));

        child.setLevel(Level.INFO);
        System.out.println("child overrides: " + child.isLoggable(Level.INFO));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 OffAllLevelsDemo.java
java OffAllLevelsDemo
~~~

**stdout thực tế**, đã biên dịch/chạy và đối chiếu:

~~~text
logger OFF: false
INFO | all.info
FINEST | all.finest
WARNING | warning.warning
child inherits OFF: false
child overrides: true
~~~

### 6.1. Giải thích thứ tự từng bước

**Bước 1 — Logger được đặt OFF.** Lệnh **logger.severe("off.severe")** không phát ra bản ghi vì Logger đang tắt. **logger.isLoggable(Level.SEVERE)** trả false, nên dòng đầu tiên là **logger OFF: false**.

**Bước 2 — Logger đặt ALL, Handler vẫn INFO.** Lệnh **logger.fine("all.fine")** đi qua kiểm tra level của Logger, nhưng Handler với ngưỡng INFO loại FINE. Lệnh **logger.info("all.info")** qua cả hai ngưỡng, nên được in ra.

**Bước 3 — Handler cũng chuyển sang ALL.** **logger.finest("all.finest")** qua cả Logger và Handler, do đó xuất hiện.

**Bước 4 — Logger đặt WARNING.** INFO bị chặn ngay ở Logger, trong khi WARNING được chấp nhận và xuất ra.

**Bước 5 — Handler đặt OFF.** SEVERE vẫn qua mức WARNING của Logger, nhưng Handler ở OFF loại nó. Không có dòng **handler.off.severe** trong output.

**Bước 6 — Kiểm tra quan hệ cha/con.** Parent Logger được đặt OFF; Child Logger lúc đầu có **level = null**, nghĩa là **kế thừa mức hiệu lực từ parent**, nên **isLoggable(INFO)** trả false. Khi child được đặt riêng **Level.INFO**, lệnh kiểm tra trả true, bất chấp parent đang OFF.

### 6.2. Tại sao ví dụ dùng Handler riêng?

Ví dụ dùng một Handler nhỏ để **kiểm soát chính xác stdout**, không phụ thuộc format, timestamp, tên luồng hoặc stderr mặc định của ConsoleHandler. **setUseParentHandlers(false)** cũng tránh bản ghi xuất hiện thêm qua Handler của root logger.

Handler minh họa **không phải một sink production**: nó không xử lý lỗi I/O phức tạp, backpressure hay đồng bộ cho nhiều thread. Dùng ConsoleHandler, FileHandler hoặc một logging backend phù hợp trong ứng dụng thật. Nếu tự viết Handler, phải tuân thủ hợp đồng publish/flush/close và ErrorManager khi cần.

## 7. OFF/ALL và cơ chế kế thừa level giữa các Logger

JUL tổ chức Logger theo cấu trúc cha/con dựa vào tên. Một Logger có thể có **level đặt trực tiếp**, hoặc **level = null** để kế thừa effective level từ ancestor gần nhất có cấu hình.

Ví dụ:

~~~text
Logger: com.example                 setLevel(OFF)
    |
    +-- com.example.payment         level = null (kế thừa OFF)
    |
    +-- com.example.order           setLevel(INFO) (mức riêng)
~~~

Hệ quả:

- **com.example.payment** không chấp nhận các sự kiện log thông thường nếu effective level của nó là OFF.
- **com.example.order** có thể chấp nhận các event INFO trở lên do có mức INFO riêng.
- Một Logger con khác có thể được cấu hình ALL; khi đó nó không kế thừa OFF của cha cho bước kiểm tra level của chính nó.
- **Logger.getLevel() == null** không có nghĩa là ALL. Nó có nghĩa Logger **chưa có level riêng**, và phải xem ancestor để biết effective level.
- **Logger.setLevel(null)** là cách trả Logger con về chế độ kế thừa. Không áp dụng tùy tiện cho root logger, vì root cần có level rõ ràng theo hợp đồng JUL.

**Một tinh tế quan trọng:** JUL có cơ chế chuyển bản ghi lên **Handler của Logger cha** khi useParentHandlers cho phép. Việc parent có level OFF **không nhất thiết khiến một record đã được Logger con chấp nhận bị lọc lại ở parent logger**; Handler của parent vẫn có level/filter riêng. Vì vậy, không nên “tắt toàn bộ namespace” chỉ bằng cách đặt một Logger cha ở OFF trong khi các Logger con vẫn có mức riêng. Hãy xác định ngưỡng từng Logger con và ngưỡng các Handler khi thiết kế chính sách.

## 8. Cấu hình trong logging.properties

JUL có thể lấy cấu hình từ tệp **logging.properties**, giúp thay ngưỡng mà không sửa các lời gọi logging trong nghiệp vụ.

Ví dụ:

~~~properties
handlers = java.util.logging.ConsoleHandler
.level = INFO
java.util.logging.ConsoleHandler.level = INFO
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter

com.example.noisy.level = OFF
com.example.diagnostics.level = ALL
~~~

Giải thích:

- **.level = INFO** đặt mức cho root logger.
- **ConsoleHandler.level = INFO** khiến console chỉ xuất record đạt ngưỡng INFO, kể cả khi Logger riêng được đặt ALL.
- **com.example.noisy.level = OFF** tắt log thông thường của Logger đó và các Logger con nào thực sự kế thừa OFF.
- **com.example.diagnostics.level = ALL** cho phép Logger diagnostics tiếp nhận các mức rất chi tiết; nhưng **ConsoleHandler đang INFO** nên FINE, FINER, FINEST vẫn không xuất qua console.
- Tùy các handler được gắn thêm và cấu hình useParentHandlers, log có thể tới những đích khác với ngưỡng khác.

Để cho console nhận cả FINEST, có thể đổi:

~~~properties
java.util.logging.ConsoleHandler.level = ALL
~~~

Nên giới hạn **Logger/package cần chẩn đoán**, tránh đặt root ALL trong môi trường nhiều request trừ khi có lý do và ngân sách log phù hợp.

Ví dụ lệnh khởi động một ứng dụng đã được biên dịch:

~~~bash
java -Djava.util.logging.config.file=logging.properties -cp out com.example.Main
~~~

Lệnh này **minh họa cách chỉ định cấu hình JUL**; nó giả định bạn có lớp **com.example.Main** và thư mục **out** chứa bytecode phù hợp, nên không phải lệnh chạy demo OffAllLevelsDemo ở mục 6. Nếu ứng dụng tự gọi **logger.setLevel(...)** sau khi nạp cấu hình, level có thể bị thay đổi bởi code. Quy trình cấu hình/nạp lại cũng phụ thuộc cách ứng dụng khởi tạo LogManager và backend đang dùng.

### 8.1. “Đã đặt ALL trong properties nhưng vẫn không thấy FINE”

Hãy kiểm tra theo thứ tự:

1. File cấu hình thực sự được JVM nạp đúng lúc chưa? Đường dẫn trong **-Djava.util.logging.config.file** có đúng không?
2. Logger đang phát record có đúng tên và đúng vị trí trong cây tên không?
3. Có code nào gọi **setLevel** sau khi cấu hình được nạp không?
4. Effective level của Logger là gì? **isLoggable(Level.FINE)** trả true hay false?
5. Handler đang nhận record là Handler nào? **Handler.getLevel()** có vẫn là INFO không?
6. Có Filter ở Logger/Handler đang từ chối record không? Logger có forward tới parent Handler không?
7. Record đã đến đích nhưng bị encoder, async pipeline hoặc collector xử lý/bỏ qua ở bước sau hay chưa?

Nếu **logger.isLoggable(Level.FINE)** là true nhưng không có output, đây là dấu hiệu cần xem **Handler/Filter/đích xuất**, không phải tiếp tục đặt Logger về ALL nhiều lần.

## 9. So sánh với các framework logging phổ biến

Khái niệm **OFF = vô hiệu hóa**, **ALL = ngưỡng bao trùm** cũng xuất hiện trong một số logging backend hiện đại. Tuy nhiên API và cấu hình khác nhau:

| Hệ logging | Vị trí OFF/ALL thường gặp | Ghi nhớ |
| --- | --- | --- |
| **java.util.logging (JUL)** | **java.util.logging.Level.OFF**, **Level.ALL** | Có trong JDK; Logger và Handler có level riêng |
| **Logback** | Level của Logback, cấu hình logger/root/appender | Chính sách lọc còn qua appender, filter và cấu hình encoder |
| **Log4j 2** | Level.OFF, Level.ALL trong hệ API/Core và cấu hình | Event phải đi qua logger configuration, filter, appender… |
| **SLF4J** | SLF4J là **facade**, provider quyết định cấu hình level | Không giả định có phương thức **logger.setLevel(ALL)** trong API Logger của SLF4J |

Khi dùng SLF4J, bạn thường phát các mức thông dụng như ERROR, WARN, INFO, DEBUG, TRACE qua facade; OFF và ALL chủ yếu nằm trong **cấu hình backend**. Không bê nguyên tên lớp, cú pháp properties hoặc hành vi bridge của JUL sang Logback/Log4j 2.

**Đặc biệt:** “ALL” trong backend không đồng nghĩa giữ toàn bộ telemetry. Sau khi log được tạo, các tầng appender, async queue, collector hoặc hệ lưu trữ vẫn có thể áp dụng filter/sampling/rate limits. “OFF” trên logger thuộc một backend cũng không nhất thiết tắt logging của thư viện đang sử dụng backend khác.

## 10. Chọn OFF, ALL hay một mức trung gian?

| Nhu cầu | Cấu hình nên cân nhắc | Lý do |
| --- | --- | --- |
| Chỉ muốn thấy lỗi nghiêm trọng | **SEVERE** | Giữ dấu hiệu lỗi quan trọng, loại level thấp |
| Muốn log vận hành thông thường | **INFO** | Cân bằng mức quan sát và lượng log cho nhiều hệ thống |
| Điều tra vấn đề trong một package | **FINE / FINER / FINEST** hoặc **ALL** có phạm vi hẹp | Thu thêm thông tin mà không làm tăng mọi nơi |
| Tạm tắt một logger sinh log vô ích | **OFF** với phạm vi rõ | Ngăn các record của logger đó khi chính sách cho phép |
| Muốn mọi mức qua một sink chẩn đoán | **Logger ALL + Handler ALL**, xét thêm Filter | Cần cả nguồn và đích đều chấp nhận |
| Muốn không xuất gì từ một Handler cụ thể | **Handler OFF** | Chặn riêng đích đó, Logger có thể còn đích khác |

Không có một level “tốt nhất” trong mọi môi trường. Việc chọn ngưỡng nên dựa vào giá trị của sự kiện, mức độ quan trọng của hệ thống, lượng traffic, chi phí log và yêu cầu lưu giữ/audit.

**Lưu ý về audit:** Nếu hệ thống có nghĩa vụ ghi nhận các sự kiện bảo mật hoặc giao dịch bắt buộc, không dùng OFF một cách tùy tiện làm mất các bản ghi đó. Logging cho chẩn đoán và audit có thể có yêu cầu độ bền, kiểm soát truy cập và cách vận chuyển khác nhau.

## 11. Các nhầm lẫn và lỗi thường gặp

### Lỗi 1 — Coi OFF là “chỉ tắt DEBUG”

**Sai:** đặt OFF vì muốn bỏ các dòng FINE nhưng vẫn thấy SEVERE.  
**Đúng:** dùng **INFO**, **WARNING** hoặc **SEVERE** theo mức bạn muốn giữ. OFF dùng để tắt logging thông thường ở điểm cấu hình.

### Lỗi 2 — Coi ALL là “ép mọi bản ghi xuất hiện”

**Sai:** set Logger.ALL rồi kết luận hệ thống mất log vì chưa thấy FINE.  
**Đúng:** xem thêm Handler level, Filter, cấu hình parent handlers, destination, async pipeline và nơi tìm log.

### Lỗi 3 — Nhầm null với ALL

**Sai:** Logger.getLevel() trả null nên mặc định là ALL.  
**Đúng:** null nghĩa là level **kế thừa** từ Logger cha. Parent có thể ở INFO, OFF hoặc một mức khác.

### Lỗi 4 — Tin rằng OFF trên parent luôn tắt mọi Logger con

**Sai:** chỉ đặt **com.example** OFF nhưng một số Logger con đã set INFO/ALL riêng.  
**Đúng:** xác minh effective level từng Logger cần quản lý; cân nhắc cả các Handler của cha khi record được forward.

### Lỗi 5 — Đặt OFF cho đúng Logger nhưng quên nhiều destination

**Sai:** nghĩ rằng một Handler OFF sẽ làm ứng dụng không phát record nào, trong khi Logger còn Handler khác đang hoạt động.  
**Đúng:** OFF của Handler chỉ chặn **đích đó**. Để kiểm soát output thực tế, kiểm tra toàn bộ các handler/appender và bridge.

### Lỗi 6 — Dùng ALL lâu dài ở nơi nhiều dữ liệu nhạy cảm

**Sai:** bật ALL toàn hệ thống rồi gửi nguyên request body, token hoặc thông tin định danh vào log.  
**Đúng:** bảo vệ dữ liệu ngay từ nơi phát sự kiện, dùng log mức thấp có thời hạn, giảm phạm vi, kiểm soát quyền truy cập và retention. OFF/ALL là **bộ điều khiển ngưỡng**, không phải cơ chế bảo vệ dữ liệu.

### Lỗi 7 — Tưởng OFF xóa lịch sử

**Sai:** đặt OFF rồi nghĩ bản ghi trong file hoặc backend sẽ biến mất.  
**Đúng:** OFF chỉ ảnh hưởng tới những sự kiện *sau khi cấu hình có hiệu lực*. Quy trình lưu giữ/xóa dữ liệu lịch sử là trách nhiệm riêng của storage/retention.

### Lỗi 8 — Trộn level của JUL với mức logging từ thư viện khác

**Sai:** đặt JUL root ALL để điều chỉnh mọi thư viện kể cả khi chúng dùng backend khác.  
**Đúng:** xác định API, provider/bridge và backend thực sự của từng thư viện; cấu hình tại lớp chính xác.

## 12. Cách tự kiểm thử cấu hình OFF/ALL

**Thử nghiệm A — Kiểm tra Logger.** Trong chương trình ở mục 6, giữ Handler ALL rồi đặt Logger lần lượt OFF, SEVERE, INFO, FINE, ALL. Phát một INFO và một FINE cho mỗi lần. Ghi lại bản ghi nào được chấp nhận bởi Logger.

**Thử nghiệm B — Kiểm tra Handler.** Giữ Logger ALL rồi đổi Handler giữa OFF, INFO và ALL. Quan sát FINE bị loại bởi Handler INFO dù Logger nhận nó.

**Thử nghiệm C — Kiểm tra kế thừa.** Tạo Logger cha đặt OFF; tạo Logger con có level null rồi setLevel(INFO). So sánh kết quả isLoggable(INFO) trước và sau.

**Thử nghiệm D — Kiểm tra filter.** Thêm một Filter vào Handler để loại các bản ghi có tiền tố “health.”. Dù Logger và Handler đều ALL, bản ghi bị Filter loại vẫn không xuất hiện.

**Thử nghiệm E — Kiểm tra log volume.** Với một thao tác lặp nhiều lần, so sánh số record và thời gian xử lý khi bật INFO với ALL. Không dùng thông số từ ví dụ nhỏ để suy ra hiệu năng production; cần benchmark theo backend và workload thực tế.

Khi kiểm tra, nên dùng **logger.isLoggable(Level.FINE)** để biết bước kiểm tra level tại Logger, nhưng **không coi kết quả true là bằng chứng record sẽ xuất ra đích**. Muốn xác minh đầu ra, phải quan sát Handler hoặc sink thực tế.

## 13. Câu hỏi tự đánh giá

**Câu 1:** Logger OFF, Handler ALL. Một record SEVERE thông thường có tới Handler không?  
**Đáp án:** Không. Logger đã loại sự kiện ở bước đầu.

**Câu 2:** Logger ALL, Handler INFO. Một record FINE có được in không?  
**Đáp án:** Không qua Handler INFO. ALL của Logger chỉ vượt qua tầng kiểm tra level ở Logger.

**Câu 3:** Logger cha OFF, Logger con có level INFO riêng. isLoggable(INFO) ở Logger con trả về gì?  
**Đáp án:** Thường trả **true** (như chương trình đã kiểm chứng), vì Logger con dùng level riêng. Còn việc có xuất record ra đích hay không phải xét Handler/Filter/propagation.

**Câu 4:** Logger.getLevel() trả null có phải Logger đang ở ALL?  
**Đáp án:** Không. Nó đang kế thừa level từ parent.

**Câu 5:** Muốn chỉ giữ WARNING và SEVERE, chọn OFF, ALL hay WARNING?  
**Đáp án:** **WARNING**, đồng thời bảo đảm Handler không đặt ngưỡng cao hơn.

**Câu 6:** OFF có làm mất lịch sử log đã lưu từ hôm qua không?  
**Đáp án:** Không. OFF điều chỉnh việc chấp nhận những sự kiện mới sau khi cấu hình có hiệu lực; lịch sử do storage và chính sách retention quản lý.

**Câu 7:** Vì sao việc bật ALL trên diện rộng có thể gây sự cố?  
**Đáp án:** Lượng record tăng mạnh có thể làm tăng CPU, I/O, bộ nhớ, dung lượng, chi phí và độ trễ; đồng thời dễ tạo dữ liệu nhạy cảm ngoài ý muốn nếu ứng dụng chưa kiểm soát việc ghi log.

## 14. Ghi nhớ cốt lõi

**OFF = tắt ở điểm ngưỡng được đặt. ALL = cho phép mọi mức ở điểm ngưỡng được đặt.** Cả hai chủ yếu là **mức cấu hình**, không phải severity nên dùng cho sự kiện nghiệp vụ.

Trong JUL, một bản ghi muốn xuất ra phải được Logger và Handler cho phép, đồng thời không bị các Filter hoặc bước vận chuyển tiếp theo chặn. **OFF ở Logger cha không tự động khóa những Logger con có level riêng**, và **ALL ở Logger không thể ép Handler INFO in bản ghi FINE**.

Khi thiết kế cấu hình, hãy luôn xác định rõ **logger nào, handler nào, mức nào, nơi xuất nào và trong thời gian bao lâu**. Đó là cách dùng OFF và ALL vừa chính xác về kỹ thuật vừa phù hợp vận hành.
