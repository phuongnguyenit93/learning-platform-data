# Tính toán trên dữ liệu tạm rồi mới công bố kết quả

## 1. Vì sao nên chuẩn bị kết quả trước khi thay đổi trạng thái?

Một phương thức Java có thể thực hiện nhiều công việc liên tiếp: kiểm tra đầu vào, tính giá trị mới, chuyển đổi collection, tạo đối tượng, rồi cập nhật trạng thái đang được các phương thức khác sử dụng. Nếu trạng thái đang hoạt động bị sửa ngay từ đầu, bất kỳ exception nào xuất hiện giữa các bước đều có thể khiến dữ liệu chỉ được cập nhật một phần.

Ví dụ, một đối tượng quản lý cấu hình lưu **quota** và danh sách **topics**. Yêu cầu nghiệp vụ là mỗi lần thêm một topic thì quota cũng tăng tương ứng. Cách làm thiếu an toàn là thêm vào danh sách trước, sau đó mới tính quota mới:

~~~java
// Mã minh họa trong một lớp đang có các trường mutable:
// List<String> topics; int quota;
topics.add(topic);
quota = Math.addExact(quota, increment);
~~~

Nếu **Math.addExact** phát hiện tràn số, nó ném **ArithmeticException** sau khi danh sách đã thay đổi. Người gọi biết lời gọi thất bại, nhưng nội dung đối tượng không còn là trạng thái trước đó. Ngay cả khi câu lệnh thứ hai không thất bại, một luồng đọc không được đồng bộ thích hợp cũng có thể nhìn thấy những lần cập nhật rời rạc.

Mẫu **tính toán trên dữ liệu tạm rồi mới công bố kết quả** giải quyết vấn đề về thứ tự thay đổi:

1. Đọc trạng thái hiện hành **S0**.
2. Kiểm tra điều kiện và tính toán trên biến cục bộ hoặc một bản sao riêng.
3. Tạo trạng thái ứng viên **S1** đã hoàn chỉnh, thỏa các bất biến.
4. Nếu một bước chuẩn bị thất bại, trả lỗi và vẫn giữ **S0**.
5. Nếu mọi bước chuẩn bị thành công, **công bố S1 tại một điểm commit rõ ràng**.

Ở đây, **công bố** (publish/commit) nghĩa là khiến trạng thái mới trở thành trạng thái được các phương thức khác sử dụng. Với một đối tượng trong bộ nhớ, điểm công bố thường là thay một tham chiếu trỏ đến snapshot bất biến. Với database, file hoặc hệ thống phân tán, điểm công bố cần cơ chế riêng của hệ tương ứng.

Mục tiêu chủ yếu là **bảo toàn trạng thái quan sát được khi lỗi xảy ra trước commit**. Cách tổ chức này giúp hiện thực mức bảo đảm **failure atomicity** cho phạm vi trạng thái cụ thể: một thao tác hoặc hoàn tất với kết quả mới, hoặc thất bại mà trạng thái cũ vẫn nguyên vẹn. Tuy nhiên, tính chất đó chỉ đúng khi mọi thay đổi thuộc phạm vi cam kết thực sự được trì hoãn đến điểm công bố.

## 2. Phân biệt dữ liệu tạm và trạng thái đã công bố

| Thành phần | Vai trò | Yêu cầu |
| --- | --- | --- |
| Trạng thái hiện hành S0 | Nguồn dữ liệu đang có hiệu lực | Không bị sửa trong giai đoạn chuẩn bị |
| Biến trung gian | Lưu kết quả tính toán như tổng, giới hạn, dữ liệu đã parse | Chưa tạo thay đổi mà người ngoài quan sát được |
| Bản sao / builder | Chứa cấu trúc dữ liệu mới đang xây dựng | Không chia sẻ các phần mutable có thể bị thay đổi ngoài ý muốn |
| Trạng thái ứng viên S1 | Đối tượng mới chứa **toàn bộ** kết quả hợp lệ | Được xác minh bất biến trước commit |
| Điểm công bố | Thao tác khiến S1 thay cho S0 | Rõ ràng, không phụ thuộc vào nhiều bước có thể lỗi |

Một giá trị **temporary** có thể là **int** cục bộ, **ArrayList** mới tạo, một **record**, một object bất biến hoặc kết quả tính toán được giữ trong transaction chưa commit. Không nhất thiết mọi bài toán đều phải tạo object mới; điều bắt buộc là công việc có thể thất bại không được làm hỏng trạng thái đang được sử dụng.

Cần phân biệt ba thao tác:

- **Sao chép:** tạo nơi chứa dữ liệu mới; có thể là shallow copy.
- **Hoàn thiện và đóng băng ứng viên:** kiểm tra tính hợp lệ, tránh để caller sửa nội dung ứng viên sau khi công bố.
- **Công bố:** thay đổi trạng thái mà phần còn lại của chương trình quan sát được.

Gọi **new ArrayList<>(oldList)** chỉ tạo một danh sách mới. Nếu phần tử của danh sách là object mutable và người khác cũng đang giữ tham chiếu đến chúng, thay đổi nội dung phần tử vẫn ảnh hưởng đến dữ liệu cũ. Một ứng viên an toàn cần kiểm soát cả alias và quyền sở hữu dữ liệu.

## 3. Ví dụ Java 17+ chạy được: chuẩn bị toàn bộ rồi thay snapshot

Ví dụ dưới đây xây một bộ cấu hình có hai thông tin gắn bó với nhau: **quota** và **topics**. Mỗi thao tác sửa cấu hình phải giữ cả hai thành phần nhất quán.

Trạng thái được gói trong **record Snapshot**. Record chứa **List<String>** được phòng vệ bằng **List.copyOf** để người gọi không thể thêm/xóa topic qua danh sách đang công bố. Phương thức **revise** dùng biến cục bộ để kiểm tra, tính toán và xây ứng viên. Chỉ câu lệnh cuối cùng **state = candidate** công bố toàn bộ kết quả.

Tạo tệp **PublishCandidateDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class PublishCandidateDemo {
    record Snapshot(int quota, List<String> topics) {
        Snapshot {
            if (quota < 0) {
                throw new IllegalArgumentException("quota cannot be negative");
            }
            topics = List.copyOf(topics);
        }
    }

    static final class TopicSettings {
        private volatile Snapshot state =
                new Snapshot(3, List.of("core"));

        Snapshot snapshot() {
            return state;
        }

        synchronized void revise(int addedQuota, String topic) {
            Objects.requireNonNull(topic, "topic");
            String cleaned = topic.strip();
            if (cleaned.isEmpty()) {
                throw new IllegalArgumentException("topic must not be blank");
            }

            Snapshot before = state;
            int nextQuota = Math.addExact(before.quota(), addedQuota);
            if (nextQuota < 0) {
                throw new IllegalArgumentException("quota cannot be negative");
            }

            List<String> nextTopics = new ArrayList<>(before.topics());
            nextTopics.add(cleaned);
            Snapshot candidate = new Snapshot(nextQuota, nextTopics);
            state = candidate;
        }
    }

    public static void main(String[] args) {
        TopicSettings settings = new TopicSettings();
        System.out.println("Initial: " + settings.snapshot());
        Snapshot beforeInvalid = settings.snapshot();

        try {
            settings.revise(2, "   ");
        } catch (IllegalArgumentException ex) {
            System.out.println("Validation failed: " + ex.getMessage());
        }
        System.out.println("Unchanged after validation: "
                + beforeInvalid.equals(settings.snapshot()));

        settings.revise(2, "  async  ");
        System.out.println("Committed: " + settings.snapshot());
        Snapshot beforeOverflow = settings.snapshot();

        try {
            settings.revise(Integer.MAX_VALUE, "more");
        } catch (ArithmeticException ex) {
            System.out.println("Arithmetic failed: " + ex.getMessage());
        }
        System.out.println("Unchanged after overflow: "
                + beforeOverflow.equals(settings.snapshot()));
        System.out.println("Final: " + settings.snapshot());
    }
}
~~~

Biên dịch và chạy với JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 PublishCandidateDemo.java
java PublishCandidateDemo
~~~

Kết quả đầu ra:

~~~text
Initial: Snapshot[quota=3, topics=[core]]
Validation failed: topic must not be blank
Unchanged after validation: true
Committed: Snapshot[quota=5, topics=[core, async]]
Arithmetic failed: integer overflow
Unchanged after overflow: true
Final: Snapshot[quota=5, topics=[core, async]]
~~~

Đầu ra này minh họa hai đường thất bại và một đường thành công:

- **Đầu vào không hợp lệ:** chuỗi topic chỉ chứa khoảng trắng bị phát hiện khi chuẩn bị. **state** chưa được gán nên snapshot trước/sau lỗi bằng nhau.
- **Thành công:** topic được chuẩn hóa bằng **strip**, quota được tính thành **5**, danh sách ứng viên hoàn chỉnh thành **[core, async]**, sau đó cả hai được công bố cùng một lần thay tham chiếu.
- **Tràn số:** **Math.addExact(5, Integer.MAX_VALUE)** ném **ArithmeticException** trước khi ứng viên hoàn chỉnh được công bố; snapshot hiện hành vẫn là **Snapshot[quota=5, topics=[core, async]]**.

Trong chương trình, **record** tự sinh **toString** và **equals** theo giá trị các thành phần, nên output và phép so sánh snapshot rõ ràng. **List.copyOf** chặn việc sửa cấu trúc danh sách qua snapshot, và **String** bất biến giúp snapshot này không chia sẻ các phần tử mutable. Khi đổi sang danh sách object mutable, cần thêm biện pháp copy/thiết kế bất biến cho phần tử.

Đoạn ví dụ đã được kiểm tra với **javac --release 17** và chạy trên JDK tương thích; output phía trên là kết quả chạy thực tế của chương trình.

## 4. Điểm nào có thể ném exception trong giai đoạn chuẩn bị?

Không chỉ lệnh **throw** tự viết mới tạo đường lỗi. Trong **revise** có nhiều điểm có thể thất bại:

| Bước chuẩn bị | Khả năng thất bại | Trạng thái đã công bố |
| --- | --- | --- |
| **Objects.requireNonNull** | **NullPointerException** nếu topic là null | Giữ S0 |
| **strip** và kiểm tra rỗng | Từ chối topic không hợp lệ | Giữ S0 |
| **Math.addExact** | **ArithmeticException** khi tràn int | Giữ S0 |
| Kiểm tra quota âm | **IllegalArgumentException** | Giữ S0 |
| Sao chép danh sách | Có thể thất bại khi tạo dữ liệu ứng viên | Giữ S0 trong phạm vi thiết kế thông thường |
| Tạo **Snapshot** | Constructor kiểm tra bất biến hoặc từ chối thành phần không hợp lệ | Giữ S0 |
| **state = candidate** | Thay tham chiếu tới kết quả hoàn chỉnh | S1 trở thành trạng thái hiện hành |

Không nên diễn giải bảng như một lời bảo đảm phục hồi khỏi mọi **Error** nghiêm trọng, sự cố JVM hoặc process bị dừng bất kỳ lúc nào. Bảng mô tả những đường exception thông thường trong mô hình trạng thái RAM.

Điểm thiết yếu: các lệnh có thể ném lỗi nằm **trước** việc công bố. Nếu đổi vị trí thành **state = candidate** rồi mới gọi callback có thể ném exception, hợp đồng “mọi exception đều giữ S0” không còn đúng. Callback thất bại sau commit có thể cần được báo là lỗi thông báo riêng, chứ không phải lỗi của thao tác cập nhật chính.

## 5. Tại sao nên dùng một snapshot chung thay vì cập nhật từng trường?

Giả sử class có hai trường độc lập:

~~~java
// Mã minh họa bên trong một class chứa các trường mutable.
int quota = 3;
List<String> topics = new ArrayList<>(List.of("core"));

void reviseUnsafe(int increment, String topic) {
    topics.add(topic); // Trạng thái thật đã thay đổi.
    quota = Math.addExact(quota, increment); // Có thể ném lỗi.
}
~~~

Với cách lưu hai trường mutable riêng, phải tính toán đúng thứ tự và xử lý cả việc ghi hai thành phần. Kể cả khi kiểm tra phép cộng trước, vẫn cần cân nhắc lỗi hoặc observer xuất hiện giữa các cập nhật. Nếu muốn tất cả reader nhìn thấy một cặp **quota + topics** nhất quán, việc gộp chúng vào một snapshot giúp biến một thao tác cập nhật nhiều trường thành một thao tác công bố tham chiếu.

Chuyển sang mô hình:

~~~text
Trước chuẩn bị:  current ──► Snapshot(quota=3, topics=[core])
                              |
Chuẩn bị riêng:              ▼
                       candidate(quota=5, topics=[core, async])
                              |
Commit một lần: current ─────┘
~~~

Sơ đồ tập trung vào **quyền quan sát**: ứng viên chưa được gắn vào **current** và cũng chưa bị rò rỉ qua API công khai. Nếu tất cả dữ liệu ứng viên đều được giữ riêng, exception trong giai đoạn tạo ứng viên không thay đổi snapshot hiện hành.

Đổi lại, cách này có thể phải cấp phát object và copy collection mỗi lần cập nhật. Với trạng thái lớn và cập nhật tần suất cao, cần cân nhắc cấu trúc dữ liệu bền vững (persistent), chia nhỏ aggregate có lý do nghiệp vụ, hoặc transaction/khóa phù hợp. Đừng phá bảo đảm nhất quán chỉ để tránh một lần cấp phát khi chưa đo được vấn đề hiệu năng thực tế.

## 6. Bảo vệ dữ liệu tạm khỏi alias và rò rỉ tham chiếu

Một bản sao chỉ có ích nếu việc sửa nó không làm thay đổi trạng thái gốc. Các tình huống sau cần phân biệt:

### 6.1 Sao chép phần vỏ nhưng dùng chung phần tử mutable

~~~java
// Mã minh họa: Task là một object mutable có setStatus(...).
List<Task> candidate = new ArrayList<>(currentTasks);
candidate.get(0).setStatus("DONE");
~~~

Danh sách mới vẫn trỏ tới cùng **Task** như danh sách cũ. **setStatus** làm thay đổi object được chia sẻ; trạng thái gốc đã thay đổi dù chưa commit. Muốn chuẩn bị riêng cần dùng value object bất biến, defensive copy từng phần tử, hoặc biểu diễn kết quả bằng các giá trị mới không đụng vào object đang được dùng chung.

### 6.2 Công bố một collection mà người khác còn quyền sửa

~~~java
// Mã minh họa: saved là cùng tham chiếu của mutable list.
List<String> candidate = new ArrayList<>(List.of("A", "B"));
this.currentList = candidate;
candidate.add("C");
~~~

Danh sách được công bố tiếp tục thay đổi sau điểm commit. Việc gán tham chiếu không tự làm collection bất biến. Có thể công bố **List.copyOf(candidate)** khi các phần tử đã phù hợp và không có mutable object chia sẻ cần bảo vệ. Trong ví dụ chạy được, record **Snapshot** luôn sao chép phòng vệ ở constructor.

### 6.3 Dữ liệu tạm vô tình được đưa ra bên ngoài

Tránh gọi listener, cache khác, logger có callback tùy biến hoặc trao tham chiếu ứng viên cho plugin trong giai đoạn chuẩn bị nếu các bên đó có thể lưu giữ/sửa dữ liệu hoặc tạo side effect. Một ứng viên không còn riêng tư thì **chưa gán state** chưa chắc nghĩa là **chưa có ai quan sát**.

### 6.4 Immutable wrapper không tương đương deep immutable

**Collections.unmodifiableList(list)** tạo view không cho sửa qua wrapper, nhưng thay đổi trực tiếp vào danh sách gốc có thể xuất hiện qua view. **List.copyOf(list)** tạo danh sách không thể sửa qua API và không phụ thuộc vào cấu trúc mutable ban đầu, nhưng vẫn không tự sao chép sâu object bên trong. Chọn cách làm dựa trên tính chất của phần tử và quyền sở hữu tham chiếu.

## 7. Công bố kết quả an toàn trong chương trình nhiều luồng

Cần giải quyết hai câu hỏi riêng:

1. **Mỗi reader có thấy snapshot hoàn chỉnh và được công bố đúng quy tắc bộ nhớ không?**
2. **Hai writer cạnh tranh có thể ghi đè mất thay đổi của nhau không?**

Trong ví dụ **PublishCandidateDemo**:

- **volatile Snapshot state** cung cấp quan hệ visibility khi một thread gán tham chiếu và thread khác đọc nó. Kết hợp snapshot bất biến, reader lấy một trạng thái hoàn chỉnh tại thời điểm đọc.
- **synchronized void revise(...)** khiến các lần cập nhật đi qua phương thức này tuần tự hóa với nhau. Mỗi writer dùng trạng thái trước đó rồi xây trạng thái mới trong cùng một vùng khóa.
- **snapshot()** trả về một đối tượng tham chiếu được đọc một lần. Nếu cần nhiều trường cùng thời điểm, lưu kết quả trả về vào một biến cục bộ rồi đọc các thuộc tính từ cùng snapshot; tránh gọi **snapshot()** nhiều lần và vô tình kết hợp dữ liệu ở hai phiên bản khác nhau.

Lưu ý: **volatile** cho phép công bố và đọc tham chiếu, nhưng **không** tự biến chuỗi “đọc S0 → tính S1 → gán S1” thành cập nhật không mất dữ liệu khi có nhiều writer. Hai writer có thể cùng đọc S0, mỗi người tính một phiên bản rồi người ghi sau ghi đè người ghi trước.

### Dùng AtomicReference và CAS khi cần cập nhật lạc quan

Một cách khác là dùng **AtomicReference<State>** với ứng viên được tính từ snapshot mỗi lần thử và chỉ commit nếu snapshot ấy còn hiệu lực. Phần mã sau là **minh họa theo ngữ cảnh**, giả sử **State** là record bất biến có các thành phần **quota**, **topics**, **ref** là **AtomicReference<State>**, và **topic** đã được kiểm tra:

~~~java
ref.updateAndGet(before -> {
    int quota = Math.addExact(before.quota(), increment);
    if (quota < 0) {
        throw new IllegalArgumentException("negative quota");
    }

    List<String> next = new ArrayList<>(before.topics());
    next.add(topic);
    return new State(quota, List.copyOf(next));
});
~~~

Hàm cập nhật có thể được gọi **nhiều lần** khi CAS không thắng do writer khác đã sửa trạng thái trước. Vì vậy hàm tính ứng viên phải **không có side effect**: đừng gửi email, gọi thanh toán, tăng counter bên ngoài, ghi tệp hoặc thay object mutable dùng chung bên trong lambda. Những tác dụng phụ đó có thể xảy ra lặp lại dù chỉ một lần cập nhật cuối cùng được công bố.

Nếu lambda ném exception trong lúc chuẩn bị, **updateAndGet** không thực hiện commit thành công cho lần gọi thất bại đó. Cũng cần ghi nhớ cập nhật của **writer khác** có thể đã xảy ra đồng thời; không được hiểu “lần gọi của tôi thất bại” là “mọi trạng thái toàn cục đều đứng yên”.

Đối với khóa thông thường, một phương thức **synchronized** như ví dụ chính dễ đọc hơn khi chi phí tính toán nhỏ. Khi dùng lock-free/CAS, đánh giá retry, pure function và nội dung công bố bằng kiểm thử đồng thời thực tế.

## 8. Quy trình thiết kế một thao tác chuẩn bị–công bố

### Bước 1: Xác định các bất biến

Viết rõ trạng thái hợp lệ: quota không âm; danh sách topic không chứa null; một cấu hình mới phải thay cả quota và topics; dữ liệu đã công bố không thể bị mutate qua tham chiếu của caller.

Nếu bất biến liên quan nhiều trường, cân nhắc biểu diễn bằng một object/record thay vì từng trường công khai.

### Bước 2: Xác định tất cả điểm có thể thất bại

Liệt kê validation, parse, tính toán có thể tràn, các constructor, copy collection, callback và I/O. Không chỉ tính những câu lệnh có từ khóa **throw**. Nếu giai đoạn tưởng là “prepare” đã gọi hệ thống bên ngoài có side effect, hãy tách side effect đó sang bài toán giao dịch riêng.

### Bước 3: Đọc và giữ một snapshot S0

Nếu trạng thái đã được gói vào một object bất biến, chỉ giữ tham chiếu **before**. Nếu các trường mutable còn rời rạc, việc đọc phải theo cơ chế đồng bộ phù hợp để không trộn dữ liệu ở nhiều thời điểm.

### Bước 4: Xây S1 bằng dữ liệu riêng

Dùng biến cục bộ; copy dữ liệu cần sửa; tạo object kết quả mới. Không cập nhật trực tiếp S0. Tránh gọi hàm chưa biết side effect lên object gốc.

### Bước 5: Xác minh S1 trước commit

Bảo đảm tất cả điều kiện nghiệm thu đã được kiểm tra. Constructor của immutable object là một vị trí tốt để bảo vệ invariant, vì không thể tạo một instance được công bố ở trạng thái sai bằng đường thông thường.

### Bước 6: Công bố một lần

Dùng một phép thay tham chiếu được đồng bộ thích hợp, hoặc compare-and-set nếu có writer cạnh tranh. Không chia một thay đổi logic thành nhiều phép gán độc lập mà reader có thể nhìn thấy từng phần.

### Bước 7: Định nghĩa hành vi sau commit

Một lần gửi notification hoặc callback sau commit có thể thất bại. Phân biệt **kết quả cập nhật trạng thái** với **kết quả thông báo** để người gọi không hiểu nhầm rằng một exception sau commit chứng minh thao tác chưa xảy ra.

## 9. Các thao tác không thể quy về một phép gán trong RAM

Mẫu này dễ áp dụng nhất khi trạng thái cần công bố nằm trong một aggregate do một nơi sở hữu. Với nguồn dữ liệu bên ngoài, việc chuẩn bị sẵn vẫn có ích nhưng không thay thế bảo đảm của công cụ lưu trữ.

### Ghi file

Nếu ghi thẳng lên file đích và quá trình ghi bị ngắt, file có thể chứa dữ liệu mới một phần. Một chiến lược là ghi đầy đủ vào **file tạm**, đóng/kiểm tra thành công, rồi thay tên/di chuyển vào vị trí đích bằng cơ chế nguyên tử nếu hệ file hỗ trợ. Java NIO cung cấp **Files.move** với **StandardCopyOption.ATOMIC_MOVE**; khi không được hỗ trợ, thao tác có thể ném **AtomicMoveNotSupportedException**. Không tự động fallback sang thao tác không nguyên tử nếu hợp đồng đòi hỏi atomic replacement. Tính nguyên tử khi thay file cũng khác bảo đảm dữ liệu tồn tại sau mất điện: durability có yêu cầu riêng về flush và hệ thống file.

### Cơ sở dữ liệu

Tính các giá trị tạm ở tầng Java không đảm bảo hai lệnh **UPDATE** cùng thành công. Dùng transaction của database nếu cả hai lệnh phải commit hoặc rollback cùng nhau, và kiểm tra phạm vi transaction, isolation, constraint và các thao tác thực sự tham gia transaction.

Tình huống điển hình là chuyển số dư giữa hai tài khoản. Nếu chỉ trừ số dư A rồi tăng số dư B, lỗi ở bước thứ hai sẽ để lại trạng thái nửa chừng. “Tính trước” giúp phát hiện lỗi đầu vào, nhưng không xử lý lỗi I/O xuất hiện giữa hai câu lệnh ghi riêng. Transaction phù hợp mới cung cấp ranh giới commit/rollback cho dữ liệu đó.

### HTTP, hàng đợi và service khác

Một request gửi đi không còn là dữ liệu tạm riêng của Java process. Timeout không chứng minh phía nhận chưa thực hiện thao tác. Retry có thể gửi lặp và gây duplicate side effect. Cần cơ chế như idempotency key, xác nhận trạng thái, outbox, quy trình bù trừ và hợp đồng thành công một phần tùy kiến trúc. Các biện pháp này có phạm vi bảo đảm khác việc gán một snapshot trong bộ nhớ.

## 10. Khi nào dùng builder, copy và mutable staging?

Không phải bài toán nào cũng cần tạo record mới cho từng phép cộng:

| Tình huống | Cách chuẩn bị phù hợp | Điểm cần lưu ý |
| --- | --- | --- |
| Tính một giá trị đơn | Biến cục bộ kiểu primitive hoặc immutable | Tính đủ và validate trước khi gán trường |
| Sửa cấu hình có nhiều thuộc tính | Builder/record ứng viên bất biến | Constructor kiểm tra bất biến; không để lộ builder |
| Cập nhật một collection | Copy collection, sửa copy, công bố copy bất biến | Shallow copy và mutable element |
| Thay graph object phức tạp | Copy theo quyền sở hữu hoặc persistent data structure | Không còn alias có thể mutate S0 |
| Nhiều writer trên cùng một snapshot | synchronized/lock hoặc AtomicReference CAS | Tránh lost update, retry side effect |
| Ghi nhiều bản ghi DB | Transaction và constraint của DB | Java staging không thay transaction |
| Thay nội dung file | File tạm + atomic move khi được hỗ trợ | Xét durability, cleanup và giới hạn file system |

Đôi khi mutable staging hợp lý để giảm số lần cấp phát: dùng một **ArrayList** tạm để nối, sắp xếp hoặc lọc; chỉ **List.copyOf** khi hoàn thiện. Điều đó an toàn khi staging list là tài sản riêng của thao tác, chưa được gắn vào trạng thái hiện hành và không có reference nào bên ngoài sửa nó trong thời gian chuẩn bị.

Một **builder** cũng chỉ thật sự là staging nếu method **build()** tạo kết quả độc lập hoặc immutable. Nếu builder chỉ chứa tham chiếu trỏ lại tới các collection mutable của trạng thái hiện hành, gọi **build()** không tự mang lại strong guarantee.

## 11. Kiểm thử bảo toàn trạng thái trước–sau exception

Một test tốt phải kiểm tra hai vấn đề: **đường thành công công bố đúng kết quả** và **đường lỗi không công bố ứng viên dở dang**. Trong chương trình chạy được ở trên, phép so sánh **beforeInvalid.equals(settings.snapshot())** và **beforeOverflow.equals(settings.snapshot())** trực tiếp chứng minh các snapshot có cùng nội dung ở hai đường thất bại.

Khi viết unit test thật, có thể tổ chức theo ma trận:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Topic hợp lệ và phép tính hợp lệ | Công bố chính xác một snapshot mới |
| Topic null | **NullPointerException**; trạng thái giữ nguyên |
| Topic chỉ có khoảng trắng | **IllegalArgumentException**; trạng thái giữ nguyên |
| Kết quả quota âm | **IllegalArgumentException**; trạng thái giữ nguyên |
| Cộng quota vượt phạm vi **int** | **ArithmeticException**; trạng thái giữ nguyên |
| Lỗi trong constructor ứng viên | Không công bố ứng viên lỗi |
| Caller cố sửa danh sách của snapshot | Thao tác sửa bị từ chối; snapshot không đổi |
| Hai writer đồng thời cập nhật | Không có lost update và không có snapshot chứa nửa kết quả |
| Callback sau commit báo lỗi | Hợp đồng phải chỉ rõ trạng thái đã commit hay chưa |

Nếu đang dùng test framework, đặt snapshot trước lời gọi, assert exception với **assertThrows**, rồi assert toàn bộ trạng thái sau lỗi. Không dừng ở **assertThrows**: một thao tác có thể ném đúng exception nhưng vẫn làm hỏng dữ liệu.

Kiểm tra bất biến cũng chưa luôn đủ để chứng minh **không đổi**. Một đối tượng vẫn có thể hợp lệ nhưng đã thay đổi một phần; hãy phân biệt yêu cầu **basic guarantee** (“vẫn hợp lệ”) và **strong guarantee** (“giữ nguyên trạng thái thuộc phạm vi cam kết”). Với hoạt động nhiều luồng, cần kiểm thử concurrency hoặc phân tích linearizability riêng; unit test tuần tự chỉ chứng minh các đường được kích hoạt.

## 12. Những lỗi thiết kế thường gặp

**Chuẩn bị bằng cách sửa trực tiếp S0.** Lệnh **clear**, **add**, **remove** hay setter gọi trên dữ liệu gốc đã là thay đổi, dù biến trung gian mang tên **candidate**. Hãy tạo object/collection riêng trước khi mutate.

**Gán trạng thái mới quá sớm.** Một lời gọi callback, phép tính hay validate có thể ném exception sau lệnh gán; người gọi có thể nhận lỗi nhưng thay đổi đã được công bố. Đẩy mọi bước có thể thất bại thuộc giai đoạn chuẩn bị lên trước commit và xác định hợp đồng riêng cho bước hậu commit.

**Chỉ sao chép shallow object graph.** Copy **List<Task>** nhưng sửa chính các **Task** chia sẻ với S0 làm hỏng tính độc lập của candidate. Dùng immutable element hoặc copy theo chiều sâu thực sự cần.

**Dùng volatile mà quên nhiều writer.** Việc công bố tham chiếu đúng visibility không giải quyết lost update. Dùng khóa hoặc CAS tùy đặc điểm contention và correctness.

**Giả định exception tự rollback.** **try/catch/finally** điều khiển đường lỗi và cleanup tài nguyên, không tự khôi phục bộ nhớ, database hay file. Muốn khôi phục phải có chiến lược trạng thái/giao dịch đã được thiết kế.

**Cho lambda CAS làm side effect.** Hàm tính ứng viên có thể chạy lặp khi retry. Lambda phải thuần túy theo nghĩa không tạo tác dụng phụ được quan sát bên ngoài và không mutate snapshot nguồn.

**Hiểu nhầm atomic publication là transaction toàn hệ thống.** Một phép thay tham chiếu duy nhất chỉ là điểm commit của aggregate trong RAM. Nó không đồng thời commit các ghi file, database, message broker hoặc request mạng.

**Không nêu rõ phạm vi bảo đảm.** Nếu sự kiện gửi sau commit có thể thất bại, hoặc thao tác có chấp nhận partial progress, API phải mô tả chính xác tác động sau exception để caller xử lý đúng.

## 13. Bảng kiểm khi áp dụng vào mã Java

Trước khi kết thúc một phương thức cập nhật trạng thái, kiểm tra lần lượt:

1. **Trạng thái:** đã gom các dữ liệu phải nhất quán vào một phạm vi rõ ràng chưa?
2. **Đường lỗi:** đã liệt kê mọi lệnh có thể ném exception trước khi hoàn tất chưa?
3. **Không mutate sớm:** quá trình chuẩn bị có giữ nguyên S0 và các mutable object mà S0 trỏ tới không?
4. **Đóng băng:** candidate có được bảo vệ khỏi sửa đổi qua alias, collection hoặc builder bị rò rỉ không?
5. **Bất biến:** đã validate đầy đủ trước khi công bố chưa?
6. **Điểm commit:** có thể xác định một hành động rõ ràng khiến S1 trở thành hiện hành không?
7. **Đồng thời:** đã đảm bảo visibility và tránh lost update nếu nhiều thread ghi chưa?
8. **Side effect:** notification, I/O, gửi event và callback đã có hợp đồng riêng cho lỗi sau commit chưa?
9. **Kiểm thử:** đã so sánh snapshot trước/sau mỗi đường lỗi và xác minh đường thành công chưa?

Kỹ thuật này chuyển phần lớn rủi ro exception sang giai đoạn **xây trạng thái ứng viên**. Nhờ giữ trạng thái cũ còn nguyên cho đến thời điểm công bố, phương thức dễ lập luận, dễ kiểm thử và dễ duy trì hơn. Giới hạn quan trọng nhất là phạm vi: chỉ có thể khẳng định bảo toàn trạng thái khi toàn bộ dữ liệu và side effect thuộc lời hứa thực sự được kiểm soát bởi điểm commit tương ứng.