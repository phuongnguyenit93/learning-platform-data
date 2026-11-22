# Hiệu năng mong đợi, trường hợp xấu và chất lượng hàm băm

## 1. Vì sao câu “HashMap có O(1)” chưa đủ?

HashMap được dùng rộng rãi vì có thể tra khóa và cập nhật ánh xạ rất hiệu quả. Tuy nhiên, nếu chỉ ghi nhớ “get là O(1)” mà bỏ điều kiện, người học dễ ngạc nhiên khi bộ dữ liệu khác làm chương trình chậm đi rõ rệt.

Độ phức tạp không chỉ phụ thuộc tên lớp. Nó còn phụ thuộc cách phân bố khóa, số ánh xạ so với dung lượng bảng, chi phí hashCode/equals, thời điểm tăng bảng và đường tìm bên trong bucket.

Tài liệu HashMap nêu hiệu năng hằng số cho các thao tác cơ bản khi hàm băm phân tán các phần tử phù hợp giữa các bucket. Đây là điều kiện quan trọng để hiểu kỳ vọng sử dụng. [Tài liệu HashMap, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).

Trong bài này, ta sẽ tách ba câu hỏi:

- Khi dữ liệu được phân bố phù hợp, mỗi thao tác thường cần xét bao nhiêu ứng viên?
- Khi nhiều khóa cùng dồn vào một nơi, công việc có thể tăng tới đâu?
- Làm sao thiết kế và kiểm chứng hàm băm mà không nhầm số phép so sánh với thời gian chạy?

Ví dụ sẽ đếm các lời gọi hashCode, equals và compareTo. Đây là bằng chứng về một phần công việc thuật toán, không phải phép đo độ trễ của hệ thống.

## 2. Mô hình chi phí và các đại lượng cần biết

Gọi:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| N | Số ánh xạ trong Map |
| C | Số bucket của bảng khi bảng đã được cấp phát |
| L | Số ứng viên tập trung trong một bucket đang xét |
| α = N/C | Số ánh xạ trung bình trên một bucket |
| H | Chi phí tính mã băm của khóa dò |
| E | Chi phí một phép so bằng khóa |
| P | Chi phí một phép so thứ tự nếu được dùng |

Đừng đọc α như số phần tử bắt buộc trong từng bucket. Một bảng có N = 8, C = 16 có α = 0,5, nhưng vẫn có thể dồn cả tám ánh xạ vào một bucket và để 15 bucket khác rỗng.

Một lần tìm có thể được hình dung là:

~~~text
tính mã băm khóa
+ chọn bucket
+ lọc ứng viên bằng thông tin mã băm
+ so bằng hoặc so thứ tự khi cần
+ đọc giá trị nếu đã tìm được khóa.
~~~

Phần tính vị trí thường là một số thao tác bit nhỏ. Phần đắt có thể nằm ở số ứng viên hoặc chính các phương thức do khóa cung cấp.

Nếu tạm coi H, E và P đều là hằng số nhỏ, ta có thể tập trung vào số nút cần xét. Nếu một khóa chứa chuỗi dài hoặc cấu trúc phức tạp, cần quay lại tính cả chi phí của chính khóa.

Ký hiệu O(1) theo N cũng không nói rằng thao tác bằng không hoặc không cấp phát bộ nhớ. Nó chỉ mô tả tốc độ tăng công việc theo đại lượng được chọn trong mô hình.

## 3. Hiệu năng mong đợi và chi phí khấu hao khác nhau

### Mong đợi: dựa vào phân bố dữ liệu

Nếu các khóa được phân vào bucket đủ đều và mức tải được kiểm soát, một lần tra thường chỉ gặp một nhóm ứng viên nhỏ. Trong mô hình bảng băm dùng chuỗi với giả thiết phân bố đều, số ứng viên trung bình có liên hệ với α; khi α bị giữ trong một khoảng hằng số, công việc tìm cũng có kỳ vọng hằng số.

Không có nghĩa mỗi bucket luôn dài bằng α, hoặc mỗi lần get chỉ kiểm tra đúng một nút. Đó là một đánh giá trên phân bố và điều kiện sử dụng, không phải bảo đảm tuyệt đối cho một khóa cụ thể.

Dữ liệu phân bố đều cũng không bắt buộc phải được sinh ngẫu nhiên. Chẳng hạn, với một miền số nguyên thích hợp và mã băm dùng đủ thông tin, các mã liên tiếp có thể phân bố tốt. Điều cần xem là phân bố thực tế sau khi đi qua cơ chế chọn bucket.

### Khấu hao: phân bổ công việc đắt lên cả chuỗi thao tác

Một lần put thêm khóa mới có thể cần tăng bảng, cấp phát và bố trí lại các nút. Lần đó có thể tốn nhiều công việc hơn các lần thêm thông thường.

Nếu tăng dung lượng theo từng bước phù hợp và băm được phân bố tốt, tổng công việc của các đợt tăng bảng được chia trên nhiều lần thêm. Vì vậy, put thường được mô tả là O(1) kỳ vọng theo khấu hao trong mô hình phù hợp.

“Khấu hao” không có nghĩa mọi lần put đều nhanh như nhau. Một yêu cầu đơn lẻ vẫn có thể gặp lần tăng bảng và có độ trễ cao hơn.

Hai khái niệm không thay thế nhau:

| Cụm từ | Giải thích điều gì? |
| --- | --- |
| Chi phí mong đợi | Điều kiện phân bố khóa làm trung bình phải xét ít ứng viên |
| Chi phí khấu hao | Một số thao tác đắt được phân bổ trên cả chuỗi thao tác |
| Chi phí trường hợp xấu | Một thao tác hoặc một dữ liệu bất lợi có thể đòi bao nhiêu công việc |

Khi đánh giá một API theo độ trễ yêu cầu đơn lẻ, không lấy một thông lượng trung bình làm bằng chứng rằng sẽ không có lần cập nhật chậm.

## 4. Các thao tác HashMap không có cùng chi phí

Bảng dưới là mô hình thực hành với khóa có hashCode/equals chi phí hằng số, và các điều kiện phân bố được nêu rõ:

| Thao tác | Đánh giá thường dùng | Điều cần giữ trong đầu |
| --- | --- | --- |
| get, containsKey, remove theo khóa | Kỳ vọng O(1) khi phân bố tốt | Trường hợp va chạm bất lợi có thể phải xét O(N) ứng viên |
| put thêm ánh xạ | Kỳ vọng O(1) theo khấu hao khi phân bố tốt | Một lần có thể phải tăng bảng hoặc xử lý bucket đông |
| put thay giá trị của khóa đã có | Cần tìm đúng khóa trước | Không được gọi là miễn phí chỉ vì size không tăng |
| containsValue | Có thể phải quét bảng và nút | Không có cùng chỉ mục băm theo giá trị |
| Duyệt toàn bộ Map | Phụ thuộc O(C + N) | Cấp phát bảng quá thưa có thể làm việc duyệt tốn hơn |
| size | O(1) trong triển khai thông thường này | Không cần duyệt để đếm lại mọi ánh xạ |

Ở một đợt tăng bảng, công việc cấp phát và phân bố lại có thể phụ thuộc C + N. Với mức tải được kiểm soát, C thường tăng cùng bậc với N nên ta hay nói gọn chi phí đợt tăng là O(N). Nếu người gọi chủ động yêu cầu một dung lượng ban đầu rất lớn, chi phí cấp phát còn phải được đánh giá theo dung lượng yêu cầu, không chỉ số ánh xạ hiện có.

Một vòng “với mỗi giá trị cần tìm, gọi containsValue” có thể biến bài toán thành nhiều lượt quét. Đừng áp dụng kết luận O(1) của tra khóa cho một phép hỏi ở phía giá trị.

Khi chỉ cần đọc cả khóa và giá trị, duyệt entrySet giúp lấy chúng từ cùng ánh xạ, tránh thêm lượt get theo từng khóa. Dù vậy, một lượt duyệt HashMap vẫn phụ thuộc cả bảng và số nút, chứ không tự trở thành một phép tra hằng số.

## 5. Chất lượng hàm băm: đúng hợp đồng trước, phân bố tốt sau

### Điều kiện đúng bắt buộc

Nếu hai đối tượng bằng nhau theo equals thì hashCode của chúng phải bằng nhau. Ngược lại, các đối tượng không bằng nhau vẫn được phép có cùng mã băm.

Một hàm băm trả 0 cho mọi khóa có thể giữ điều kiện bắt buộc này. Nó không sai chỉ vì gây va chạm; vấn đề là hiệu năng có thể rất kém. [Hợp đồng Object.hashCode, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html).

Trong khi đó, nếu equals coi hai khóa là cùng một đối tượng nghiệp vụ nhưng hashCode cho hai mã khác nhau, đó là lỗi tính đúng. HashMap có thể tìm ở những nơi không phù hợp trước khi có cơ hội dùng equals. Không xử lý lỗi này như một chuyện tối ưu tốc độ.

### Phân bố có ích cho dữ liệu thực

Một hàm băm phù hợp cần dùng thông tin nhận diện có ý nghĩa và tạo đủ khác biệt trên miền khóa thực tế. Các lựa chọn sau thường tạo phân bố xấu:

~~~text
Trả một hằng số cho mọi khóa.
Chỉ dùng một cờ boolean cho hàng triệu khóa.
Chỉ dùng độ dài tên khi đa số tên có cùng độ dài.
Bỏ qua phần số thứ tự trong khóa gồm nhóm và số thứ tự.
Ghép nhiều trường bằng một phép có quá nhiều đối xứng trên dữ liệu thực.
~~~

Ví dụ khóa có hai trường x, y. Nếu hash chỉ là x + y thì các cặp (1, 9), (2, 8), (3, 7) cùng mã 10. Điều này không tự vi phạm hợp đồng, nhưng dữ liệu có cấu trúc như vậy có thể làm va chạm nhiều hơn dự kiến.

Mục tiêu không phải “mã băm khác nhau cho mọi khóa”. Điều đó không thể bảo đảm cho một miền đối tượng lớn hơn miền int. Mục tiêu là giữ đúng hợp đồng và tránh một cách băm tự làm mất phần lớn thông tin phân biệt của dữ liệu cần lưu.

### Mã khác nhau vẫn có thể chung bucket

Bảng có số bucket hữu hạn. Hai mã khác nhau vẫn có thể bị ánh xạ tới cùng một chỉ số. Đánh giá chất lượng chỉ bằng việc đếm số hashCode phân biệt chưa mô tả hết phân bố bucket.

OpenJDK có xử lý một phần bit của mã băm trước khi chọn vị trí. Cơ chế đó có thể giúp những khác biệt ở phần bit cao tham gia phân bố, nhưng không tạo ra khác biệt khi mọi khóa đều trả cùng một mã. Một bước trộn nội bộ không thay được thiết kế hashCode phù hợp.

### Dữ liệu khóa phải ổn định

Tính đúng và hiệu năng đều khó diễn giải nếu khóa thay đổi các trường tham gia equals/hashCode sau khi được đưa vào Map. Khi đó, bạn không chỉ đang gặp một phép tra chậm; bạn có thể không tìm được ánh xạ qua đường tra bình thường.

Dùng khóa bất biến hoặc dữ liệu nhận diện ổn định giúp phân tích phân bố có ý nghĩa. Một record có trường String và số nguyên là ví dụ đơn giản; record chứa một collection có thể sửa vẫn cần xem xét nội dung bên trong.

## 6. Trường hợp xấu: khi nhiều khóa chung một mã

Trong một bucket dạng chuỗi, nếu có L khóa cần phân biệt, tìm một khóa không tồn tại có thể phải xét toàn bộ L ứng viên. Khi L = N, số ứng viên cần xét có thể tăng tuyến tính theo tổng số ánh xạ.

Không chỉ số bucket chung mới quan trọng. Nếu nhiều ứng viên có cùng toàn bộ mã băm nội bộ, bước so mã không loại được chúng và cần thêm phép nhận diện khóa. Một hàm băm hằng số tạo đúng tình huống đó.

Sự khác biệt khi N tăng:

~~~text
Phân bố tốt:
N tăng nhưng nhóm ứng viên trung bình vẫn nhỏ
-> chi phí tra kỳ vọng không tăng theo N.

Tất cả chung mã:
N tăng làm nhóm khó phân biệt lớn hơn
-> một lần tìm vắng có thể phải xét gần toàn bộ nhóm.
~~~

Nếu mỗi lần thêm một khóa mới cũng phải loại trừ nhiều khóa cũ trước khi xác nhận chưa tồn tại, tổng công việc xây Map trong một dữ liệu bất lợi có thể tăng mạnh, thậm chí theo bậc hai. Không thể lấy chi phí kỳ vọng của một lần put trong điều kiện tốt để cam kết tổng thời gian cho dữ liệu va chạm có hệ thống.

Nâng dung lượng không tự giải quyết tình trạng mọi khóa có cùng mã. Chúng tiếp tục chọn cùng một bucket ở mỗi dung lượng. Muốn hiểu cải thiện từ việc tăng bảng, phải phân biệt va chạm do mặt nạ bucket với trùng hoàn toàn mã băm.

## 7. Bucket dạng cây giúp gì và không bảo đảm điều gì?

OpenJDK có thể chuyển bucket đông sang cấu trúc cây theo các điều kiện triển khai. Cây cân bằng giảm chiều cao, nhưng muốn tìm theo một nhánh còn cần đủ thông tin để quyết định nên đi về phía nào.

Khi mã băm khác nhau, hoặc khi các khóa có quan hệ Comparable phù hợp để phân biệt các khóa cùng mã, thuật toán có thể dùng thông tin đó chọn hướng. Với các khóa có cùng mã, không so thứ tự được và không bằng khóa đang xét, một phép tìm có thể phải thăm nhiều nhánh để không bỏ sót một khóa bằng nhau.

Đường tìm `TreeNode.find` trong OpenJDK 17 thể hiện nhánh thử nhiều cây con khi không xác định được hướng so sánh phù hợp. Vì thế, “bucket đã thành cây” không tự suy ra “mọi get chắc chắn O(log N)” với mọi loại khóa. [Mã nguồn HashMap, OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/HashMap.java).

Một hình minh họa:

~~~text
                 nhiều khóa có cùng mã
                         |
          +--------------+--------------+
          |                             |
so được thứ tự phân biệt        không có hướng phân biệt
          |                             |
có thể chọn một nhánh            có thể phải xét nhiều nhánh
mỗi bước tìm                     để loại trừ khóa bằng nhau
~~~

Đây là cách đọc thuật toán, không phải một tuyên bố rằng Comparable luôn cần được thêm vào mọi khóa chỉ để tối ưu HashMap.

Nếu dùng Comparable, quan hệ so sánh phải đúng và phù hợp dữ liệu. Một compareTo luôn trả 0 cho những khóa khác nhau không cung cấp khả năng chọn hướng đang cần. Không thêm một thứ tự tùy tiện hoặc vi phạm hợp đồng rồi kỳ vọng nó sửa được một hàm băm kém.

Trong bài thí nghiệm, lớp khóa có thứ tự dùng id, cũng là dữ liệu xác định equals. Điều đó tạo một ví dụ rõ ràng về hai trường hợp cùng mã: không có thứ tự phân biệt và có thứ tự phân biệt.

## 8. Chương trình Java 17+ đếm công việc khi tra cứu

Tệp `HashMapCostDemo.java` tạo ba kiểu khóa bất biến:

| Lớp | Cách băm | Có Comparable không? |
| --- | --- | --- |
| SpreadKey | Trả id | Không |
| SameHashKey | Luôn trả 0 | Không |
| OrderedSameHashKey | Luôn trả 0 | Có, so id |

Chương trình dùng các id từ 0 tới N - 1, rồi tìm id -1 không có trong Map. Trước lượt tìm này, các bộ đếm được đặt lại nên không gồm chi phí dựng Map. Sau đó chương trình còn kiểm tra một khóa có thật để bảo đảm thí nghiệm không chỉ tạo một tập dữ liệu không tra được.

Dung lượng khởi tạo 64 được chọn để các trường hợp nhiều khóa cùng mã có thể đi vào cơ chế bucket cây của OpenJDK 17. Không dùng phản chiếu truy cập bảng riêng tư. Các con số đếm cụ thể là quan sát của thí nghiệm được đối chiếu với mã nguồn, không phải hợp đồng số lần gọi cố định cho mọi phiên bản JVM.

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.function.IntFunction;

public class HashMapCostDemo {
    static long hashCalls;
    static long equalsCalls;
    static long compareCalls;

    record SpreadKey(int id) {
        @Override
        public int hashCode() {
            hashCalls++;
            return id;
        }

        @Override
        public boolean equals(Object other) {
            equalsCalls++;
            return other instanceof SpreadKey key && id == key.id;
        }
    }

    record SameHashKey(int id) {
        @Override
        public int hashCode() {
            hashCalls++;
            return 0;
        }

        @Override
        public boolean equals(Object other) {
            equalsCalls++;
            return other instanceof SameHashKey key && id == key.id;
        }
    }

    record OrderedSameHashKey(int id) implements Comparable<OrderedSameHashKey> {
        @Override
        public int hashCode() {
            hashCalls++;
            return 0;
        }

        @Override
        public boolean equals(Object other) {
            equalsCalls++;
            return other instanceof OrderedSameHashKey key && id == key.id;
        }

        @Override
        public int compareTo(OrderedSameHashKey other) {
            compareCalls++;
            return Integer.compare(id, other.id);
        }
    }

    static void resetCounts() {
        hashCalls = 0;
        equalsCalls = 0;
        compareCalls = 0;
    }

    static <K> void measure(
            String label, int n, IntFunction<K> keyFactory) {
        Map<K, Integer> map = new HashMap<>(64);
        for (int id = 0; id < n; id++) {
            map.put(keyFactory.apply(id), id);
        }

        resetCounts();
        Integer missing = map.get(keyFactory.apply(-1));
        long missHash = hashCalls;
        long missEquals = equalsCalls;
        long missCompare = compareCalls;

        Integer found = map.get(keyFactory.apply(n - 1));
        boolean correct = map.size() == n
                && missing == null
                && found != null
                && found == n - 1;
        if (!correct) {
            throw new AssertionError("Unexpected map result");
        }

        System.out.println(label + " n=" + n
                + " missingHash=" + missHash
                + " missingEquals=" + missEquals
                + " missingCompare=" + missCompare
                + " correct=" + correct);
    }

    public static void main(String[] args) {
        for (int n : new int[] {32, 64, 128}) {
            measure("spread", n, SpreadKey::new);
            measure("sameHash", n, SameHashKey::new);
            measure("orderedSameHash", n, OrderedSameHashKey::new);
        }

        Map<SameHashKey, Integer> small = new HashMap<>(64);
        for (int id = 0; id < 4; id++) {
            small.put(new SameHashKey(id), id);
        }
        resetCounts();
        Integer missing = small.get(new SameHashKey(-1));
        System.out.println("small collision n=4 missing=" + missing
                + " equals=" + equalsCalls);

        Map<SpreadKey, Integer> map = new HashMap<>();
        map.put(new SpreadKey(7), 10);
        Integer previous = map.put(new SpreadKey(7), 20);
        System.out.println("equal key replacement old=" + previous
                + " size=" + map.size()
                + " value=" + map.get(new SpreadKey(7)));
    }
}
~~~

Biên dịch và chạy với JDK 17 hoặc mới hơn hỗ trợ phiên bản đích:

~~~shell
javac --release 17 -encoding UTF-8 HashMapCostDemo.java
java HashMapCostDemo
~~~

Chương trình dùng cú pháp và API tương thích Java 17. Nó không cần thư viện ngoài, không đo thời gian và không in thứ tự duyệt Map.

Stdout chính xác:

~~~text
spread n=32 missingHash=1 missingEquals=0 missingCompare=0 correct=true
sameHash n=32 missingHash=1 missingEquals=33 missingCompare=0 correct=true
orderedSameHash n=32 missingHash=1 missingEquals=5 missingCompare=3 correct=true
spread n=64 missingHash=1 missingEquals=0 missingCompare=0 correct=true
sameHash n=64 missingHash=1 missingEquals=65 missingCompare=0 correct=true
orderedSameHash n=64 missingHash=1 missingEquals=6 missingCompare=4 correct=true
spread n=128 missingHash=1 missingEquals=0 missingCompare=0 correct=true
sameHash n=128 missingHash=1 missingEquals=129 missingCompare=0 correct=true
orderedSameHash n=128 missingHash=1 missingEquals=7 missingCompare=5 correct=true
small collision n=4 missing=null equals=4
equal key replacement old=10 size=1 value=20
~~~

### Giải thích các cột

`missingHash` là số lời gọi hashCode trong lần tìm khóa vắng. `missingEquals` là số lời gọi equals của khóa. `missingCompare` là số lời gọi compareTo. Chúng được chụp lại trước khi chạy phép kiểm tra khóa có thật.

`correct=true` xác nhận size đúng N, khóa -1 không được tìm thấy và khóa N - 1 vẫn lấy đúng giá trị. Nó không có nghĩa dữ liệu có hiệu năng tốt.

Các bộ đếm tĩnh chỉ dành cho quan sát trong chương trình một luồng. Không đưa cách đếm này vào một phép đo hiệu năng nhiều luồng rồi coi nó là không có tác động lên việc chạy.


## 9. Đọc kết quả: công việc tăng theo dữ liệu nào?

### Khóa phân bố phù hợp

Với SpreadKey, các id của ví dụ tạo mã băm đủ phân biệt cho những bảng đang dùng. Tìm -1 cho `missingEquals=0` ở cả ba kích thước.

Không được kết luận lượt tìm không làm việc gì. Nó vẫn gọi hashCode một lần, xử lý vị trí và kiểm tra thông tin trong bảng. Trong ví dụ, mã của khóa vắng không khớp các mã đã lưu ở nơi được chọn, nên không cần equals để loại ứng viên.

Điều quan sát có giá trị là khi N tăng trong những bộ này, công việc so bằng không tăng theo N. Nó phù hợp với kỳ vọng của một bảng được phân bố tốt, nhưng không chứng minh mọi bộ khóa dùng hashCode trả id đều không bao giờ có va chạm.

### Khóa cùng mã và không có thứ tự

Với SameHashKey:

| N | missingEquals |
| --- | --- |
| 32 | 33 |
| 64 | 65 |
| 128 | 129 |

Số phép so bằng tăng gần tuyến tính theo N. Phép tìm vắng cần loại trừ các khóa cùng mã, thay vì được dẫn thẳng theo một quan hệ thứ tự phân biệt.

Tại sao N + 1 thay vì N? Trong đường tìm quan sát ở triển khai này, có một kiểm tra nút đầu trước khi đi vào hàm tìm trên cây; nút đó có thể được so bằng lại trong đường tìm cây. Hằng số thêm một không thay đổi kết luận về tốc độ tăng.

Trường hợp nhỏ N = 4 có bốn lần equals, phù hợp với việc xét một chuỗi nhỏ. Từ các con số này, không tự rút ra số nút chính xác cần để mọi Map chuyển cây. Chuyển dạng còn phụ thuộc điều kiện triển khai, và ta không đo trực tiếp mọi sự kiện nội bộ bằng bộ đếm equals.

### Khóa cùng mã nhưng có thứ tự nhất quán

Với OrderedSameHashKey:

| N | missingEquals | missingCompare |
| --- | --- | --- |
| 32 | 5 | 3 |
| 64 | 6 | 4 |
| 128 | 7 | 5 |

Trong thí nghiệm, khi số khóa tăng gấp đôi, số phép so tăng chậm. Quan hệ compareTo theo id cho phép chọn hướng thay vì thử nhiều nhánh.

Đó là minh chứng cho tác dụng của thông tin thứ tự trong một trường hợp cụ thể. Không phải một khuyến nghị viết hashCode hằng số rồi thêm Comparable để biến nó thành thiết kế băm tốt. Cả nhóm vẫn dồn vào một bucket, và quá trình hoạt động còn tốn các phép so thứ tự.

Muốn phát biểu một bảo đảm cho ứng dụng, cần xác định loại khóa, các quan hệ so sánh, miền dữ liệu và phiên bản triển khai. Ba dòng đo ở đây không thay thế cho phân tích đó.

### Thay giá trị theo khóa bằng nhau

Dòng cuối cho thấy put một khóa mới bằng khóa cũ giữ size bằng một và thay giá trị từ 10 thành 20. Một phép thêm thử theo khóa cần phát hiện khóa đã có; chất lượng băm không được phép làm thay đổi ngữ nghĩa “mỗi khóa có một ánh xạ”.

Sự đúng của kết quả và số công việc là hai tiêu chí riêng. Nhóm SameHashKey vẫn tra đúng nhưng cần nhiều phép so hơn.

## 10. Thiết kế một khóa băm thực tế

### Chọn đúng dữ liệu nhận diện

Ví dụ một khách hàng được xác định bởi khu vực và số khách hàng:

~~~java
record CustomerKey(String region, long number) {
}
~~~

Với dữ liệu thành phần phù hợp, record tạo equals/hashCode dựa trên các thành phần. Đây thường là điểm khởi đầu dễ kiểm tra hơn một lớp tự viết thiếu một trong hai phương thức.

Nếu tự cài hashCode, hãy dùng cùng ý nghĩa nhận diện như equals. Một hàm băm chỉ lấy độ dài region và bỏ qua number có thể khiến nhiều khách hàng của cùng khu vực đổ vào rất ít mã.

Đừng thêm dữ liệu không thuộc danh tính chỉ để “làm mã đa dạng”: nếu equals bỏ qua trường đó mà hashCode lại phụ thuộc nó, hai đối tượng bằng nhau có thể có mã khác nhau. Tối ưu phân bố không được phá điều kiện đúng.

Nếu nghiệp vụ so một chuỗi không phân biệt hoa thường hoặc có chuẩn hóa mã, quy tắc đó phải được áp dụng nhất quán khi tạo khóa và tính cả equals/hashCode. Một phía chuẩn hóa còn phía kia không chuẩn hóa sẽ tạo dữ liệu khó tra hoặc đồng nhất sai khóa.

### Trộn trường có chủ đích

`Objects.hash` hoặc cơ chế sinh mã của record có thể giúp triển khai một khóa nhiều trường theo mẫu quen thuộc. Chúng không bảo đảm không có va chạm trên mọi bộ dữ liệu, và vẫn phải được dùng trên đúng các trường nhận diện.

Không tự sửa hashCode bằng một công thức ngẫu nhiên chỉ vì một phép đo nhỏ cho ít va chạm hơn. Hãy giữ một thiết kế có hợp đồng rõ, thử trên dữ liệu đại diện và chỉ tối ưu thêm khi đã thấy vấn đề đáng kể.

Với dữ liệu có cấu trúc, chú ý những nhóm thường gặp: mã cùng tiền tố, nhiều số liên tiếp, nhiều khóa cùng loại hoặc nhiều trường có giá trị cố định. Chất lượng cần được đánh giá trên những nhóm đó, không chỉ trên một tập sinh ngẫu nhiên.

### Đúng bằng nhau chưa đủ rẻ để so

Một khóa có mã phân bố tốt nhưng hashCode mỗi lần phải đi qua hàng nghìn phần tử có thể vẫn làm get chậm. Tương tự, equals có thể phải xét nhiều dữ liệu dù chỉ được gọi một lần.

Có thể chọn một định danh bất biến gọn hơn nếu nó thật sự biểu diễn cùng danh tính cần tra. Không cắt bớt thông tin cần thiết rồi coi việc hai thực thể bị nhập làm một là một cải thiện hiệu năng.

Đối với khóa bất biến mà việc tính hash thực sự đắt, một thiết kế có thể tính và giữ lại mã một cách an toàn. Việc đó phải bảo đảm dữ liệu liên quan không thay đổi; giữ một mã cũ trong khóa có thể sửa sẽ làm lỗi hợp đồng, không phải một tối ưu hợp lệ.

Cũng không suy ra mọi kiểu khóa đều tính lại cùng lượng dữ liệu ở mọi lần hashCode. Chẳng hạn, một số lớp có cơ chế tối ưu nội bộ; muốn đánh giá chi phí cụ thể phải đọc hợp đồng hoặc triển khai của đúng kiểu đang dùng.

## 11. Dung lượng và hệ số tải: tối ưu theo cả thời gian lẫn bộ nhớ

Hệ số tải liên quan thời điểm tăng bảng. Giữ bảng quá chật có thể tăng số ứng viên; giữ bảng quá thưa làm tốn nhiều vị trí hơn và ảnh hưởng các công việc phải duyệt bảng.

Nếu dự kiến N ánh xạ và hệ số tải f, mô hình tính dung lượng cần thiết để tránh chạm ngưỡng là khoảng:

~~~text
C cần ít nhất gần N / f.
~~~

Ví dụ N = 1000, f = 0,75:

~~~text
1000 / 0,75 ≈ 1333,33.
~~~

Trong OpenJDK 17, dung lượng bảng theo lũy thừa của hai, nên mức dung lượng thực phù hợp có thể lớn hơn con số chia này. Đây là lý do không đồng nhất đối số dung lượng khởi tạo với “số phần tử được chứa mà chắc chắn không tăng bảng”.

Khi làm việc với Java 17, constructor `new HashMap<>(initialCapacity)` nhận một dung lượng ban đầu yêu cầu. Nó không phải hạn ngạch số ánh xạ và không làm Map tự từ chối khóa mới khi size đạt đối số đó.

Chọn dung lượng nên dựa trên số liệu thực và kiểu công việc:

| Công việc chính | Điều cần cân nhắc |
| --- | --- |
| Nạp một lần nhiều ánh xạ đã biết trước quy mô | Dung lượng phù hợp có thể giảm các đợt tăng bảng |
| Map nhỏ và thay đổi thường xuyên | Cấp phát rất lớn thường không có cơ sở |
| Duyệt báo cáo nhiều lần | Bảng quá thưa có thể làm phải xét nhiều vị trí trống |
| Dữ liệu va chạm hoàn toàn mã băm | Chỉ tăng dung lượng không tách được các khóa đó |
| Hệ thống nhạy độ trễ một yêu cầu | Quan sát các lần tăng bảng, cấp phát và thu gom bộ nhớ, không chỉ trung bình |

Việc cấp sẵn nhiều hơn có thể giảm một số công việc về sau nhưng tăng chi phí bộ nhớ và cấp phát đầu kỳ. Không có một dung lượng hoặc hệ số tải được chọn tùy tiện là tốt nhất cho mọi ứng dụng.

Trong các cấu trúc dùng vùng nhớ động, số đối tượng nút, số ô bảng và dữ liệu khóa/giá trị cùng góp phần vào tổng bộ nhớ. Không đánh giá bộ nhớ chỉ bằng size.

Nếu Map đã quá lớn so với nhu cầu thật, hãy xem xét vòng đời và cách thay thế cấu trúc khi phù hợp. Điều đó là một quyết định quản lý dữ liệu; không tự xóa rồi dựng lại giữa lúc người khác đang sử dụng hoặc giả định một thao tác dọn dữ liệu sẽ cung cấp mọi bảo đảm về dung lượng.

## 12. Đo thời gian để trả lời đúng câu hỏi

Bộ đếm phương thức giúp nhìn ra số ứng viên cần so, nhưng không phản ánh toàn bộ thời gian chạy. Một lần equals rất rẻ có thể khác xa một lần equals trên dữ liệu lớn; số lần gọi bằng nhau cũng chưa bao gồm bộ nhớ đệm CPU, cấp phát, JIT hoặc thu gom bộ nhớ.

Khi cần đo tốc độ trong JVM, JMH là công cụ do OpenJDK phát triển để xây dựng phép đo ở nhiều quy mô. [Dự án JMH](https://github.com/openjdk/jmh).

Một phép đo có ý nghĩa nên định nghĩa rõ:

- Đo tra thành công, tra không thành công hay một tỷ lệ hỗn hợp?
- Đo get trên Map đã dựng, hay đo cả tạo khóa và dựng Map?
- Đo put thêm khóa mới, thay giá trị cũ hay một đợt có tăng bảng?
- Dữ liệu là khóa cùng tham chiếu đã lưu hay đối tượng mới bằng dữ liệu khóa?
- Kích thước và phân bố khóa có đại diện cho ứng dụng không?
- Có cần quan sát độ trễ từng lượt và mức sử dụng bộ nhớ ngoài thông lượng không?

Tách bước dựng dữ liệu khỏi phần cần đo nếu mục tiêu là tra cứu. Nếu mục tiêu là nạp dữ liệu, phải đưa việc dựng vào phần đo. Cùng một mã có thể trả lời hai câu hỏi khác nhau tùy cách đặt ranh giới đo.

Để kết quả có thể diễn giải, cần giai đoạn làm nóng, các lần chạy độc lập phù hợp, giữ kết quả được sử dụng và kiểm soát những công việc ngoài mục tiêu như in văn bản trong phần đo. Ghi lại JDK, cấu hình và dữ liệu thử để so sánh có cơ sở.

Không suy ra một kết luận chung về HashMap từ việc bấm giờ vài thao tác trên một Map rất nhỏ. Một mẫu mà toàn bộ dữ liệu vừa nằm trong bộ nhớ đệm và không có resize đang mô tả một điều kiện thuận lợi cụ thể.

Chương trình bài học cố ý không dùng System.nanoTime để đưa ra một con số nanosecond có vẻ tuyệt đối. Nó chọn câu hỏi hẹp hơn có thể kiểm tra rõ: số phép gọi phương thức khóa thay đổi thế nào khi phân bố và khả năng so thứ tự thay đổi.

Nếu kết quả thời gian không giống dự đoán từ số lần equals, hãy tìm thành phần chi phí còn thiếu trong mô hình. Không vội kết luận phân tích độ phức tạp sai chỉ vì một dữ liệu nhỏ có hằng số khác.

## 13. Những suy luận cần tránh

| Suy luận | Điều bị bỏ qua | Cách phát biểu chính xác hơn |
| --- | --- | --- |
| Mọi get đều O(1) trong mọi dữ liệu | Điều kiện phân bố và chi phí khóa | Kỳ vọng hằng số khi các điều kiện phù hợp |
| Put O(1) nên không có lần chậm | Chi phí tăng bảng và cấp phát | Đánh giá khấu hao và quan sát lượt riêng |
| Bucket thành cây nên mọi tra cứu O(log N) | Khả năng định hướng tìm theo mã/thứ tự | Nêu rõ loại khóa và đường tìm hỗ trợ |
| HashCode hằng số là sai hợp đồng | Hợp đồng chỉ yêu cầu khóa bằng nhau cùng mã | Có thể đúng ngữ nghĩa nhưng kém hiệu năng |
| Nhiều mã khác nhau nghĩa là không có va chạm bucket | Mã vẫn phải nén về số bucket hữu hạn | Xét phân bố sau chọn bucket |
| Tăng dung lượng sẽ chữa mọi va chạm | Trùng toàn bộ mã băm | Cần xem lại thiết kế mã và dữ liệu |
| Ít equals là tổng chi phí nhỏ | Hash, so thứ tự, bộ nhớ và công việc khác | Dùng mô hình chi phí đầy đủ |
| correct=true nghĩa là nhanh | Chỉ kiểm tra kết quả chức năng | Đánh giá tính đúng và hiệu năng riêng |
| Comparable là cách thay thế một hashCode tốt | Thứ tự chỉ hỗ trợ một số trường hợp | Giữ chất lượng băm là mục tiêu chính |
| HashMap an toàn nhiều luồng vì phép tra nhanh | Tính đồng thời độc lập với độ phức tạp | Dùng hợp đồng truy cập phù hợp |
| Đo get bằng cùng đối tượng đã lưu đại diện mọi truy vấn | Cùng tham chiếu có thể tránh equals | Thử cả khóa cùng đối tượng và khóa mới bằng dữ liệu |
| Chỉ cần dữ liệu ngẫu nhiên | Dữ liệu thực có cấu trúc và nhóm va chạm | Kết hợp dữ liệu đại diện và trường hợp bất lợi |

Các thông số hiệu năng cần gắn với điều kiện cụ thể. Một hệ thống có nhiều truy vấn khóa vắng có thể bộc lộ va chạm khác với một hệ thống chủ yếu tra cùng vài khóa nóng. Một Map phải dựng lại liên tục cũng khác một Map được dựng một lần rồi chỉ đọc.

## 14. Bài tập và lời giải

### Bài 1 — Giải thích O(1) đúng điều kiện

Một người nói: “HashMap.get luôn mất cùng một số bước dù dữ liệu thế nào”. Cần sửa câu này ra sao?

**Lời giải:** get có hiệu quả kỳ vọng hằng số khi mã băm phân bố tốt và chi phí thao tác khóa được tính phù hợp. Một bucket đông hoặc hàm hashCode/equals đắt có thể làm một lượt tra tốn hơn. O(1) cũng không khẳng định mọi lần có đúng cùng số bước.

### Bài 2 — α có giới hạn bucket dài nhất không?

N = 8, C = 16, α = 0,5. Có thể kết luận mỗi bucket chứa tối đa một phần tử không?

**Lời giải:** không. α là trung bình trên toàn bảng; dữ liệu có thể dồn nhiều hoặc toàn bộ ánh xạ vào một bucket. Muốn đánh giá trường hợp xấu phải xét phân bố chứ không chỉ tỷ lệ trung bình.

### Bài 3 — Kỳ vọng và khấu hao

Một lần put gặp tăng bảng nên chậm hơn rõ rệt. Có mâu thuẫn với mô tả put có chi phí kỳ vọng khấu hao hằng số không?

**Lời giải:** không. Khấu hao phân bổ các lần đắt lên cả chuỗi thao tác; không hứa mọi thao tác đơn lẻ đều rẻ. Tính kỳ vọng về phân bố khóa là một điều kiện khác cần giữ.

### Bài 4 — Hash hằng số có luôn làm sai kết quả?

Mọi khóa trả hashCode bằng 0 nhưng equals so đúng dữ liệu bất biến. Map có bắt buộc trả sai kết quả không?

**Lời giải:** không. Các khóa bằng nhau vẫn cùng mã, nên điều kiện cần có thể được giữ. Kết quả vẫn có thể đúng nhưng tra cứu phải làm nhiều công việc hơn. Chương trình cho correct=true với SameHashKey nhưng số equals tăng tuyến tính.

### Bài 5 — Diễn giải N + 1

Ở N = 128, SameHashKey có missingEquals bằng 129. Có phải HashMap đang lưu 129 khóa không?

**Lời giải:** không; size vẫn 128. Đường tìm của triển khai có thể kiểm tra lại một nút ở giai đoạn khác, tạo thêm một lần equals. Số lần gọi không phải số nút phân biệt được lưu.

### Bài 6 — Cây có đủ bảo đảm logarit không?

Hai khóa không bằng nhau có cùng mã, không so thứ tự được. Vì sao cây cân bằng vẫn chưa bảo đảm mỗi bước chỉ đi một nhánh tìm?

**Lời giải:** chiều cao nhỏ không tự cho biết khóa bằng dữ liệu đang nằm về phía nào khi mã và thông tin thứ tự không phân biệt được. Để không bỏ sót khóa bằng nhau, thuật toán có thể phải tìm nhiều nhánh. Cần xét quy tắc định hướng, không chỉ hình dạng cây.

### Bài 7 — Thiết kế khóa nhiều trường

CustomerKey có region và number, equals xét cả hai. HashCode chỉ dùng độ dài region. Đây là lỗi đúng/sai hay trước hết là nguy cơ hiệu năng?

**Lời giải:** nếu các đối tượng bằng nhau luôn có cùng region và number thì độ dài region cũng bằng nhau, nên cách băm có thể vẫn giữ điều kiện bắt buộc. Nhưng nó mất gần hết thông tin phân biệt giữa các khách hàng và có thể phân bố rất kém. Một thiết kế dùng các thành phần nhận diện phù hợp sẽ dễ đạt phân bố hữu ích hơn.

### Bài 8 — Hàm băm dùng trường equals không xét

Equals chỉ xét mã khách hàng, còn hashCode dùng thêm thời điểm cập nhật. Hai đối tượng cùng mã nhưng thời điểm khác nhau có thể gặp vấn đề gì?

**Lời giải:** chúng bằng nhau theo equals nhưng có thể có mã băm khác, vi phạm hợp đồng. Đây là lỗi tính đúng, không chỉ va chạm hay chậm. Loại bỏ sự không nhất quán trước khi tối ưu tốc độ.

### Bài 9 — Chọn dung lượng

Dự kiến 1000 ánh xạ và hệ số tải 0,75. Vì sao không nên mặc định đối số constructor 1000 là số ánh xạ chắc chắn chứa được trước khi tăng bảng?

**Lời giải:** đối số là dung lượng yêu cầu, còn ngưỡng tăng phụ thuộc dung lượng thực và hệ số tải. Mô hình cần khoảng N/f, rồi còn quy tắc dung lượng của triển khai. Đồng thời phải cân nhắc bộ nhớ, không tăng tùy tiện tới một con số rất lớn.

### Bài 10 — Đo nhầm công việc

Một phép đo dựng Map, sinh khóa, gọi get và in kết quả cho mỗi lượt. Có thể gọi toàn bộ thời gian đó là độ trễ get của Map đã dựng không?

**Lời giải:** không. Nó gồm nhiều công việc khác với tra cứu. Nếu cần đo get, chuẩn bị dữ liệu ngoài phần đo và sử dụng kết quả theo một phương pháp phù hợp. Nếu muốn đo cả quy trình, mô tả kết quả là thời gian quy trình đó.

### Bài 11 — Đếm equals bằng 0

SpreadKey cho missingEquals bằng 0. Có thể kết luận lượt tra không đọc bảng hoặc không có chi phí không?

**Lời giải:** không. Nó vẫn tính hashCode, xử lý vị trí và có các kiểm tra nội bộ. Bộ đếm chỉ cho biết không cần gọi equals trong trường hợp đã quan sát.

### Bài 12 — Cấu trúc giá trị và khóa đắt

Map có N rất nhỏ, nhưng hashCode của khóa phải duyệt một danh sách dài M phần tử mỗi lần. Khi nói get là O(1) theo N, còn thiếu điều gì?

**Lời giải:** còn chi phí theo M của chính khóa. Một mô hình đầy đủ phải tính H, không chỉ số nút trong bucket. Nếu danh sách còn có thể đổi khi khóa đang được lưu, đó còn là nguy cơ vi phạm tính ổn định của khóa.

## 15. Quy trình đánh giá hiệu năng có cơ sở

Trước hết, kiểm tra equals/hashCode và sự ổn định của khóa để bảo đảm kết quả đúng. Sau đó mô tả dữ liệu thật: số ánh xạ, nhóm khóa, tỷ lệ truy vấn thành công và thất bại, số lần cập nhật, nhu cầu duyệt.

Dùng một thí nghiệm kiểm soát được để nhìn số công việc khi cần giải thích cơ chế. Khi cần con số thời gian, tạo phép đo có ranh giới rõ và phù hợp JVM. Tách kết luận về một bộ dữ liệu cụ thể khỏi lời hứa cho toàn ứng dụng.

HashMap có hiệu năng mong đợi tốt khi mã băm giữ đúng hợp đồng, phân bố phù hợp và chi phí khóa được kiểm soát. Trường hợp xấu vẫn cần được hiểu, nhất là khi nhiều khóa cùng mã hoặc khi một lần cập nhật phải làm thêm công việc cấp phát và tăng bảng.

