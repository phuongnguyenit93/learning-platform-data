# Lỗi khóa khả biến và rủi ro cập nhật đồng thời

## 1. Hai nguồn lỗi khác nhau cần được nhận diện

Một HashMap có thể trả kết quả bất ngờ dù chương trình chỉ có một luồng: đối tượng dùng làm khóa đã bị sửa những thông tin xác định nó là ai.

Một HashMap cũng có thể gặp lỗi khi nhiều luồng cùng truy cập và cập nhật mà không có cơ chế phối hợp phù hợp: thao tác đọc, sửa và duyệt không còn diễn ra theo giả định tuần tự.

Hai vấn đề không phải một:

| Vấn đề | Câu hỏi cần trả lời |
| --- | --- |
| Khóa khả biến | Dữ liệu tham gia equals/hashCode có còn ổn định khi khóa đang nằm trong Map không? |
| Cập nhật đồng thời | Các luồng có một hợp đồng truy cập bảo vệ được dữ liệu và toàn bộ thao tác nghiệp vụ không? |

Khóa bất biến không tự làm HashMap an toàn luồng. Một ConcurrentHashMap cũng không tự làm đối tượng khóa đang thay đổi trở nên hợp lệ cho tra cứu băm.

Bài học giải thích cơ chế, cung cấp thí nghiệm chạy được và chỉ ra những cách tổ chức dữ liệu phù hợp. Các ví dụ sai về khóa được ghi nhận như quan sát của một trạng thái đã vi phạm điều kiện sử dụng, không phải một hành vi mà mọi Map phải bảo đảm.

## 2. Khóa khả biến sai ở điểm nào?

HashMap định vị ánh xạ bằng mã băm từ khóa, rồi kiểm tra khóa để tìm đúng dữ liệu. Khi đưa một khóa vào, cấu trúc nội bộ lưu thông tin phục vụ định vị tại thời điểm đó.

Giả sử khóa có trường id; hashCode và equals đều dựa vào id:

~~~text
Lúc thêm:
key.id = 1
ánh xạ được bố trí theo mã của id 1.

Sau khi sửa:
key.id = 2
lần tra mới tính mã theo id 2.
~~~

Đối tượng khóa vẫn là cùng một đối tượng trong bộ nhớ, nhưng dữ liệu định vị mới không còn khớp với dữ liệu khi ánh xạ được tạo.

Điều này có thể dẫn tới tình huống quan sát được: get(key) không tìm thấy giá trị, size vẫn còn một ánh xạ, và duyệt khóa vẫn gặp chính đối tượng đó. Nó không phải bằng chứng HashMap “đánh mất tham chiếu”; vấn đề là đường tìm theo khóa đã không còn dùng cùng định danh.

Hợp đồng Map nêu hành vi không được xác định khi một đối tượng khóa bị thay đổi theo cách ảnh hưởng tới so bằng trong lúc đang được dùng làm khóa. Không thiết kế ứng dụng dựa vào một kết quả hỏng cụ thể của tình trạng này. [Tài liệu Map, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

### Cùng tham chiếu chưa chắc cứu được phép tìm

Một hiểu nhầm phổ biến là “tôi truyền đúng đối tượng đã put nên chắc chắn get được”. Trong cách tìm băm, còn có bước chọn vị trí và kiểm tra mã đã lưu trước khi cùng tham chiếu trở thành thông tin hữu ích.

Nếu khóa tạo mã khác sau khi bị sửa, đối tượng có thể nằm ở nơi mà lần tra mới không tìm tới, hoặc bị loại bởi mã băm không còn khớp. Vì vậy, đừng dùng == như một lý do cho phép thay đổi dữ liệu nhận diện khóa.

### Không phải mọi thay đổi của đối tượng khóa đều phá hợp đồng băm

Một đối tượng có thể có mã định danh bất biến và một nhãn mô tả có thể sửa. Nếu equals/hashCode chỉ dùng mã định danh ổn định, việc thay nhãn không nhất thiết làm hỏng tra cứu.

Tuy nhiên, nhãn vẫn là dữ liệu có thể chia sẻ giữa các luồng và cần một chính sách truy cập riêng nếu bị sửa đồng thời. Tính ổn định của nhận diện khóa và tính an toàn khi sửa mọi trường của đối tượng là hai điều khác nhau.

## 3. Chọn khóa ổn định và tránh bất biến nông

Với một tài khoản có id ổn định:

~~~java
record AccountKey(int id) {
}
~~~

Khóa gồm dữ liệu bất biến đơn giản, nên một đối tượng AccountKey mới có cùng id có thể được dùng để tìm ánh xạ cũ. Không cần giữ và dùng lại cùng một tham chiếu khóa.

Ngược lại, chỉ khai báo biến khóa bằng final chưa làm đối tượng được trỏ tới bất biến:

~~~java
final MutableKey key = new MutableKey(1);
key.changeId(2);
~~~

Final ở đây ngăn gán biến key sang đối tượng khác; nó không chặn lời gọi sửa đối tượng.

### Record chứa collection vẫn cần xem xét nội dung

Đoạn sau không tự đóng băng danh sách:

~~~java
record GroupKey(List<String> parts) {
}
~~~

Nếu một danh sách được truyền vào rồi bị sửa qua tham chiếu bên ngoài, nội dung tham gia equals/hashCode của record có thể đổi theo.

Một cách thiết kế với thành phần String trong ví dụ:

~~~java
record GroupKey(List<String> parts) {
    GroupKey {
        parts = List.copyOf(parts);
    }
}
~~~

Constructor lấy một bản sao cấu trúc danh sách không cho sửa. Do các phần tử String là bất biến, nội dung dùng để nhận diện khóa trong ví dụ được giữ ổn định trước việc bên ngoài sửa danh sách đầu vào.

List.copyOf không phải sao chép sâu mọi phần tử. Nếu phần tử là một đối tượng có thể sửa và equals/hashCode của GroupKey phụ thuộc nội dung đối tượng đó, còn phải quyết định cách bảo vệ thành phần ấy.

Chính sách null cũng cần rõ: List.copyOf trong ví dụ không nhận danh sách null hoặc phần tử null. Đó là một phần của hợp đồng tạo khóa đã chọn, không phải quy định chung cho mọi khóa Map.

### Cùng một khóa có thể được dùng ở nhiều Map

Sao chép các ánh xạ sang một Map khác thường vẫn dùng chung đối tượng khóa. Nếu khóa bị sửa sau đó, nhiều cấu trúc có thể cùng gặp vấn đề.

Đổi lớp Map hoặc tạo một bản sao nông không thay thế cho việc tạo một giá trị khóa ổn định. Cần quyết định dữ liệu nhận diện tại nơi xây khóa, thay vì hy vọng cấu trúc chứa nó tự bảo vệ.

## 4. HashMap không cung cấp cơ chế đồng bộ nội bộ

HashMap không được đồng bộ hóa sẵn. Khi nhiều luồng cùng truy cập và có cập nhật cấu trúc, cần đồng bộ từ bên ngoài theo một cơ chế phù hợp. [Tài liệu HashMap, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).

Cập nhật cấu trúc gồm thêm hoặc xóa ánh xạ. Thay giá trị cho một khóa đang có không tăng size và thường không được gọi là thay đổi cấu trúc, nhưng điều đó **không** tự làm thao tác thay giá trị an toàn để nhiều luồng thực hiện thiếu phối hợp.

Có ba yêu cầu dễ bị trộn lẫn:

| Yêu cầu | Ý nghĩa |
| --- | --- |
| Trạng thái nội bộ nhất quán | Cấu trúc chứa ánh xạ được truy cập theo hợp đồng |
| Khả năng nhìn thấy cập nhật | Luồng đọc có quan hệ bộ nhớ phù hợp để nhìn thấy trạng thái được công bố |
| Tính nguyên tử của thao tác nghiệp vụ | Những bước cần đi liền nhau không bị một thao tác khác chen vào làm sai kết quả |

Một khóa String bất biến chỉ giúp phần nhận diện; nó không cung cấp cả ba điều trên cho HashMap.

Khai báo biến tham chiếu Map là volatile cũng không tự biến chuỗi get rồi put thành một thao tác nguyên tử. Volatile có quan hệ công bố/nhìn thấy theo mô hình bộ nhớ, không thay được một quy tắc cập nhật ghép nhiều bước. Cơ chế khóa và quan hệ happens-before cần được áp dụng đúng với dữ liệu chia sẻ. [Java Language Specification 17, chương Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html).

Không mô tả lỗi đồng thời bằng một kết quả duy nhất bắt buộc như “luôn ném ngoại lệ” hoặc “luôn mất đúng một cập nhật”. Khi thiếu hợp đồng truy cập, kết quả có thể phụ thuộc lịch thực thi. Một kiểm tra chạy qua được chưa chứng minh rằng cách truy cập đã đúng.

## 5. Khóa từng lời gọi chưa đủ cho thao tác ghép

Giả sử bộ đếm đang bằng 0. Hai tác vụ đều muốn tăng một:

~~~text
Tác vụ A đọc 0.
Tác vụ B đọc 0.
Tác vụ A ghi 1.
Tác vụ B ghi 1.
Kết quả cuối: 1, dù đã có hai yêu cầu tăng.
~~~

Lỗi này gọi là mất cập nhật: tác vụ sau ghi đè một kết quả được tính từ trạng thái cũ.

Nó vẫn có thể xảy ra khi mỗi get và mỗi put riêng lẻ đều được bảo vệ bằng khóa, nếu phần “đọc rồi tính rồi ghi” không nằm trong cùng một vùng được bảo vệ.

Ví dụ minh họa phạm vi khóa chưa đủ:

~~~java
int before;
synchronized (lock) {
    before = map.get("count");
}

// Một tác vụ khác có thể đọc hoặc cập nhật ở khoảng giữa.

synchronized (lock) {
    map.put("count", before + 1);
}
~~~

Các biến map và lock được giả sử đã có. Mã này bảo vệ từng truy cập Map bằng cùng lock, nhưng không bảo vệ quyết định dựa trên before.

Cách thể hiện toàn bộ phép tăng dưới một khóa:

~~~java
synchronized (lock) {
    map.put("count", map.get("count") + 1);
}
~~~

Điều kiện để cách này đúng là mọi bên liên quan đến dữ liệu đó tuân thủ cùng cơ chế khóa và các tiền điều kiện của phép tăng, như khóa count luôn có một số nguyên hợp lệ.

Nếu một bên dùng lock A, bên khác dùng lock B, hai vùng synchronized không tự ngăn nhau. Nếu một bên vẫn truy cập thẳng Map ngoài quy tắc, hợp đồng chung lại bị phá.

## 6. Chương trình Java 17+ có kết quả kiểm chứng rõ

Chương trình sau có ba nhóm:

1. Thay id của một khóa đang ở HashMap và ConcurrentHashMap, thực hiện tuần tự để quan sát lỗi nhận diện khóa.
2. Dùng khóa bất biến và sao chép danh sách thành phần để giữ khóa ổn định.
3. Hai tác vụ tăng bộ đếm bằng vùng khóa bị tách, vùng khóa đầy đủ và ConcurrentHashMap.compute.

Ở ví dụ mất cập nhật, mỗi truy cập HashMap vẫn nằm trong synchronized. CountDownLatch buộc hai tác vụ đọc xong trước khi tác vụ nào được ghi, nên kết quả 1 được tạo bởi lịch phối hợp có chủ đích. Đây là minh chứng phạm vi nguyên tử sai, không chạy một cuộc ghi không đồng bộ lên HashMap rồi chờ lỗi tình cờ.

Tệp `HashMapSafetyDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class HashMapSafetyDemo {
    static final class MutableKey {
        private int id;

        MutableKey(int id) {
            this.id = id;
        }

        void changeId(int id) {
            this.id = id;
        }

        @Override
        public int hashCode() {
            return id;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof MutableKey key && id == key.id;
        }
    }

    record AccountKey(int id) {
    }

    record GroupKey(List<String> parts) {
        GroupKey {
            parts = List.copyOf(parts);
        }
    }

    static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected safe-case result");
        }
    }

    static void awaitBoth(Future<Void> first, Future<Void> second)
            throws Exception {
        first.get(10, TimeUnit.SECONDS);
        second.get(10, TimeUnit.SECONDS);
    }

    static int splitCriticalSections(ExecutorService pool) throws Exception {
        Map<String, Integer> map = new HashMap<>();
        map.put("count", 0);
        Object lock = new Object();
        CountDownLatch bothRead = new CountDownLatch(2);
        Callable<Void> task = () -> {
            int before;
            synchronized (lock) {
                before = map.get("count");
            }
            bothRead.countDown();
            if (!bothRead.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Both readers did not arrive");
            }
            synchronized (lock) {
                map.put("count", before + 1);
            }
            return null;
        };
        Future<Void> first = pool.submit(task);
        Future<Void> second = pool.submit(task);
        awaitBoth(first, second);
        synchronized (lock) {
            return map.get("count");
        }
    }

    static int wholeCriticalSection(ExecutorService pool) throws Exception {
        Map<String, Integer> map = new HashMap<>();
        map.put("count", 0);
        Object lock = new Object();
        Callable<Void> task = () -> {
            for (int i = 0; i < 1000; i++) {
                synchronized (lock) {
                    map.put("count", map.get("count") + 1);
                }
            }
            return null;
        };
        Future<Void> first = pool.submit(task);
        Future<Void> second = pool.submit(task);
        awaitBoth(first, second);
        synchronized (lock) {
            return map.get("count");
        }
    }

    static int atomicCompute(ExecutorService pool) throws Exception {
        Map<String, Integer> map = new ConcurrentHashMap<>();
        map.put("count", 0);
        Callable<Void> task = () -> {
            for (int i = 0; i < 1000; i++) {
                map.compute("count", (key, old) -> old + 1);
            }
            return null;
        };
        Future<Void> first = pool.submit(task);
        Future<Void> second = pool.submit(task);
        awaitBoth(first, second);
        return map.get("count");
    }

    public static void main(String[] args) throws Exception {
        MutableKey key = new MutableKey(1);
        Map<MutableKey, String> hash = new HashMap<>();
        Map<MutableKey, String> concurrent = new ConcurrentHashMap<>();
        hash.put(key, "value");
        concurrent.put(key, "value");
        System.out.println("before mutation hash=" + key.hashCode()
                + " hashMap=" + hash.get(key)
                + " concurrent=" + concurrent.get(key));

        key.changeId(2);
        System.out.println("observed after mutation hash=" + key.hashCode()
                + " hashMap=" + hash.get(key)
                + " concurrent=" + concurrent.get(key));
        System.out.println("observed sizes after mutation="
                + hash.size() + "," + concurrent.size());
        System.out.println("observed stored key same reference="
                + hash.keySet().stream().anyMatch(stored -> stored == key));

        Map<AccountKey, String> accounts = new HashMap<>();
        accounts.put(new AccountKey(7), "stable");
        String stable = accounts.get(new AccountKey(7));
        check(Objects.equals(stable, "stable"));
        System.out.println("immutable key lookup=" + stable);

        List<String> input = new ArrayList<>(List.of("team", "A"));
        GroupKey group = new GroupKey(input);
        Map<GroupKey, String> groups = new HashMap<>();
        groups.put(group, "group-value");
        input.set(1, "B");
        String groupValue = groups.get(new GroupKey(List.of("team", "A")));
        check(Objects.equals(groupValue, "group-value"));
        System.out.println("defensive key lookup=" + groupValue);
        System.out.println("defensive key parts=" + group.parts());
        try {
            group.parts().add("C");
            throw new AssertionError("Expected unmodifiable parts");
        } catch (UnsupportedOperationException exception) {
            System.out.println("parts modification=UnsupportedOperationException");
        }

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            int split = splitCriticalSections(pool);
            int whole = wholeCriticalSection(pool);
            int atomic = atomicCompute(pool);
            check(split == 1);
            check(whole == 2000);
            check(atomic == 2000);
            System.out.println("split critical sections count=" + split
                    + " expected=2");
            System.out.println("whole critical section count=" + whole);
            System.out.println("concurrent compute count=" + atomic);
            System.out.println("safe-case checks=PASS");
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 -encoding UTF-8 HashMapSafetyDemo.java
java HashMapSafetyDemo
~~~

Dùng JDK 17 hoặc mới hơn hỗ trợ phiên bản đích 17. Mã dùng API và cú pháp tương thích Java 17.

Stdout của lần chạy kiểm chứng:

~~~text
before mutation hash=1 hashMap=value concurrent=value
observed after mutation hash=2 hashMap=null concurrent=null
observed sizes after mutation=1,1
observed stored key same reference=true
immutable key lookup=stable
defensive key lookup=group-value
defensive key parts=[team, A]
parts modification=UnsupportedOperationException
split critical sections count=1 expected=2
whole critical section count=2000
concurrent compute count=2000
safe-case checks=PASS
~~~

Các dòng có nhãn observed ghi lại hành vi đã thấy sau khi sửa khóa; không phải một yêu cầu rằng mọi triển khai Map phải xử lý một khóa vi phạm điều kiện theo đúng cách đó. Những check trong mã không dùng các kết quả quan sát ấy làm điều kiện đúng.

### Vì sao thí nghiệm đồng thời có kết quả xác định?

Cả hai tác vụ chỉ ghi sau khi CountDownLatch xác nhận cả hai đã đọc. Vì chưa có lần ghi nào trước đó, chúng cùng giữ before bằng 0. Hai lần ghi sau được khóa riêng nhưng đều ghi 1; thứ tự của chúng không thay kết quả.

Ví dụ wholeCriticalSection thực hiện 1000 lượt tăng cho mỗi tác vụ và giữ cả get/put trong cùng vùng khóa. Hai tác vụ hoàn tất cho 2000.

Ví dụ atomicCompute dùng ConcurrentHashMap với khóa count đã được khởi tạo bằng 0, không có bên nào xóa khóa. Mỗi compute tăng từ giá trị hiện tại theo hợp đồng nguyên tử của loại Map đó, nên hai nhóm 1000 lượt cũng cho 2000.

Chương trình chờ Future hoàn tất để nhận kết quả và truyền lỗi tác vụ ra luồng chính. Giới hạn chờ giúp lỗi phối hợp không biến thành chờ vô hạn trong ví dụ; nó không tham gia tính đúng của bộ đếm. ExecutorService được dừng trong finally.

### Vì sao ConcurrentHashMap vẫn gặp lỗi khóa?

Hai Map ở phần đầu giữ cùng một đối tượng MutableKey. Sửa id làm dữ liệu nhận diện đổi ở cả hai nơi. Việc ConcurrentHashMap bảo vệ truy cập cấu trúc đồng thời không tự chuyển ánh xạ sang một định danh mới hợp lệ.

Trong lần chạy, size vẫn là một nhưng get bằng khóa đã đổi trả null ở cả hai Map. Từ đó phải rút ra yêu cầu giữ khóa ổn định, không phải một quy trình “đổi id rồi dùng size để sửa lại Map”.


## 7. Chọn một hợp đồng truy cập phù hợp

### Một nơi sở hữu dữ liệu và truy cập tuần tự

Nếu Map thuộc một tác vụ, một đối tượng có quyền sở hữu rõ hoặc một luồng duy nhất, HashMap là lựa chọn tự nhiên khi những yêu cầu khác phù hợp.

Hạn chế làm lộ chính Map hoặc đối tượng khóa có thể sửa ra ngoài nơi sở hữu. Một phương thức trả thẳng keySet, values hoặc entrySet của Map nội bộ có thể làm lộ thêm đường thay đổi ánh xạ.

Quyền sở hữu rõ giúp giảm nhu cầu đồng bộ, nhưng vẫn cần khóa có nhận diện ổn định. Một luồng duy nhất cũng có thể tạo lỗi khóa khả biến như phần đầu chương trình.

### HashMap cùng một khóa bảo vệ chung

Với dữ liệu được nhiều luồng truy cập, có thể giữ một đối tượng lock riêng và yêu cầu mọi thao tác liên quan tuân theo nó.

Điều cần xác định không chỉ là “có synchronized hay chưa”, mà là:

- Dữ liệu nào được bảo vệ bởi lock?
- Một thao tác nghiệp vụ gồm những bước nào phải nằm trong cùng vùng?
- Những lượt duyệt hoặc sao chép có dùng cùng cơ chế không?
- Có đường nào bỏ qua lock qua Map gốc, góc nhìn hoặc đối tượng giá trị không?

Với phép tăng trong chương trình, phạm vi cần bảo vệ là đọc số hiện tại, tính số mới và ghi số mới. Với thao tác chuyển giữa hai khóa, có thể còn nhiều trạng thái phải đi cùng nhau hơn.

Đặt lock ở nơi sở hữu dữ liệu và giữ nó ổn định thường rõ hơn việc mỗi phương thức tạo một `new Object()` để synchronized. Các lock mới khác nhau không phối hợp truy cập tới cùng Map.

### Collections.synchronizedMap

Có thể bọc:

~~~java
Map<String, Integer> counters =
        Collections.synchronizedMap(new HashMap<>());
~~~

Mọi truy cập vào cấu trúc nền cần đi qua đối tượng được trả về hoặc các góc nhìn của nó theo đúng quy tắc. Không giữ một tham chiếu khác rồi dùng thẳng HashMap nền để bỏ qua lớp bọc.

Nếu tự ghép nhiều lời gọi thành một phép tăng, bảo vệ cả chuỗi bằng monitor của lớp bọc:

~~~java
synchronized (counters) {
    int current = counters.getOrDefault("count", 0);
    counters.put("count", current + 1);
}
~~~

Đoạn này giả sử bộ đếm không được lưu null và mọi bên tuân thủ cùng hợp đồng. Việc lớp bọc đồng bộ từng get và put không tự làm một chuỗi get–tính–put tự viết trở thành một thao tác không thể xen ngang.

Khi duyệt các collection view bằng iterator, spliterator hoặc stream, hợp đồng synchronizedMap yêu cầu đồng bộ trên chính Map được trả về. Khóa trên `counters.keySet()` là một monitor khác và không thay cho việc khóa counters. [Tài liệu Collections.synchronizedMap, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map)).

Nếu cần một bản dữ liệu để xử lý lâu bên ngoài vùng khóa, có thể sao chép trong vùng được bảo vệ rồi xử lý bản sao:

~~~java
Map<String, Integer> snapshot;
synchronized (counters) {
    snapshot = new HashMap<>(counters);
}
~~~

Với khóa String và giá trị Integer bất biến trong ví dụ, bản sao cấu trúc có cách diễn giải đơn giản. Nếu khóa hoặc giá trị chứa đối tượng có thể sửa, bản sao nông chưa tự bảo vệ nội dung sâu khỏi các tác vụ khác.

### ConcurrentHashMap và thao tác nguyên tử theo hợp đồng

ConcurrentHashMap hỗ trợ truy cập đồng thời và có các thao tác như putIfAbsent, replace có điều kiện, compute hoặc merge với bảo đảm phù hợp. Với một bộ đếm theo khóa, compute như chương trình giúp giữ phép tính và cập nhật trong thao tác nguyên tử được lớp đó định nghĩa. [Tài liệu ConcurrentHashMap, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

Những giới hạn cần hiểu:

- Chuỗi get rồi put tự viết vẫn là hai thao tác, dù từng thao tác riêng an toàn luồng.
- Một compute cho một khóa không tự tạo giao dịch nhiều khóa.
- Hàm tính cần ngắn, không sửa lại chính Map bên trong.
- ConcurrentHashMap không nhận khóa hoặc giá trị null được lưu.
- Khóa vẫn phải giữ đúng hợp đồng nhận diện và mã băm.
- Đối tượng giá trị có thể sửa vẫn cần chính sách truy cập riêng.

Không thay HashMap bằng ConcurrentHashMap rồi giữ nguyên mọi giả định nghiệp vụ cũ. Ví dụ một ứng dụng dùng null như trạng thái đã tra cứu nhưng không tìm thấy cần mô hình giá trị khác trước khi đổi lớp Map.

Các phương thức compute của Map nói chung cũng không có một lời hứa nguyên tử chung cho mọi triển khai. Cần dựa vào hợp đồng của loại được dùng, thay vì chỉ thấy tên phương thức giống nhau.

## 8. Map an toàn luồng không tự bảo vệ giá trị bên trong

Giả sử Map chứa danh sách công việc:

~~~java
Map<String, List<String>> tasks = new ConcurrentHashMap<>();
tasks.computeIfAbsent("team", key -> new ArrayList<>()).add("job");
~~~

ConcurrentHashMap có thể bảo vệ việc đặt hoặc lấy ánh xạ team tới danh sách. Nhưng add tác động lên ArrayList được trả về; nó không tự được mọi thao tác Map bảo vệ như một hành động trên danh sách.

Nếu nhiều luồng cùng sửa danh sách đó, cần một kiểu giá trị hỗ trợ cách dùng đồng thời hoặc cơ chế khóa đúng cho nó. Một hướng khác là cập nhật bằng các giá trị bất biến mới và chỉ thay ánh xạ theo một quy tắc nguyên tử phù hợp.

Tương tự, một giá trị có trường count có thể sửa không tự được bảo vệ chỉ vì nó được lưu trong ConcurrentHashMap. Cần phân biệt bốn lớp trách nhiệm:

~~~text
Nhận diện khóa
    -> ổn định của equals/hashCode.

Cấu trúc Map
    -> hợp đồng truy cập và cập nhật ánh xạ.

Thao tác nghiệp vụ nhiều bước
    -> phạm vi nguyên tử đúng.

Nội dung đối tượng giá trị
    -> cơ chế đọc/sửa riêng phù hợp.
~~~

Sửa được một lớp không đồng nghĩa các lớp còn lại đều đã đúng.

Điều này cũng giải thích vì sao một lớp bọc chỉ đọc chưa làm dữ liệu sâu bất biến. Người giữ một đối tượng giá trị có thể vẫn sửa chính đối tượng đó qua một tham chiếu khác.

## 9. ConcurrentModificationException là tín hiệu bắt lỗi, không phải hàng rào an toàn

Một iterator của HashMap có thể phát hiện thay đổi cấu trúc trái quy tắc và ném ConcurrentModificationException. Nhưng việc phát hiện là cơ chế hỗ trợ bắt lỗi theo khả năng của triển khai, không phải một hệ thống đồng bộ.

Ngoại lệ này không nhất thiết có hai luồng. Một luồng duy nhất vừa dùng for-each vừa xóa trực tiếp qua Map cũng có thể vi phạm hợp đồng iterator. [Tài liệu ConcurrentModificationException, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ConcurrentModificationException.html).

Ví dụ minh họa cách dùng không phù hợp:

~~~java
for (String key : map.keySet()) {
    if (key.startsWith("old-")) {
        map.remove(key);
    }
}
~~~

Muốn xóa khi đang duyệt trong một ngữ cảnh tuần tự phù hợp, dùng iterator.remove của chính iterator đang xét hoặc một phép lọc được hỗ trợ. Nếu có cập nhật từ các luồng khác, còn phải tuân thủ cơ chế phối hợp của nguồn; đổi phương thức xóa không tự giải quyết mọi cạnh tranh.

Đừng xử lý bằng cách bắt ConcurrentModificationException rồi tiếp tục coi kết quả duyệt dở là một bản chụp đầy đủ. Cũng đừng kết luận “không có ngoại lệ nên cách dùng nhiều luồng an toàn”. Lỗi nhìn thấy dữ liệu hoặc mất cập nhật không cần phát sinh ngoại lệ này.

Đối với một loại Map đồng thời, iterator có thể có hợp đồng duyệt khác. Việc một iterator không ném ngoại lệ khi có cập nhật cũng không tự có nghĩa nó chụp toàn bộ Map ở một thời điểm duy nhất.

Nếu cần dữ liệu báo cáo nhất quán theo một thời điểm hoặc cần bất biến trên nhiều ánh xạ, hãy thiết kế cơ chế lấy bản chụp hoặc vùng đọc phù hợp với yêu cầu ấy.

## 10. Đổi khóa và xử lý dữ liệu đã vi phạm điều kiện

### Khi định danh thật sự cần thay đổi

Thay vì sửa id của một đối tượng đang làm khóa, có thể dùng các đối tượng khóa bất biến và một thao tác thay ánh xạ rõ ràng.

Với khóa mới khác khóa cũ, quy trình nghiệp vụ cần quyết định:

1. Khóa cũ có tồn tại không?
2. Khóa mới đã có ánh xạ chưa và xử lý xung đột thế nào?
3. Giá trị nào được chuyển?
4. Các bên đọc có được thấy trạng thái giữa lúc xóa và thêm không?
5. Nếu một bước thất bại thì trạng thái mong muốn là gì?

Nếu toàn bộ quá trình phải xuất hiện như một thay đổi không thể xen ngang, bảo vệ nó bằng cơ chế thích hợp. Hai lời gọi remove và put liên tiếp trên ConcurrentHashMap vẫn không tự tạo giao dịch thay khóa.

Nếu định danh cũ vốn cần được giữ để liên kết dữ liệu ngoài, việc thay nó còn là một quyết định của mô hình nghiệp vụ. Không coi đổi một trường Java là đủ để cập nhật mọi quan hệ liên quan.

### Nếu khóa đã bị sửa khi còn trong Map

Đừng giả định gọi remove bằng khóa đã đổi chắc chắn tìm được ánh xạ cũ, hoặc put lại đối tượng đó chắc chắn chỉ “sửa vị trí” mà không có hậu quả khác. Bạn đã rời khỏi điều kiện sử dụng được hợp đồng bảo đảm.

Một lần dựng lại Map từ các tham chiếu khóa đang hỏng có thể không khôi phục được danh tính ban đầu. Hai khóa đã bị sửa thành bằng nhau còn có thể gây xung đột khi dựng lại.

Cách xử lý cần bắt đầu từ nguồn dữ liệu có thể xác định đúng danh tính, dừng những cập nhật gây vấn đề và xây lại trạng thái theo một chính sách xung đột rõ ràng trong ngữ cảnh kiểm soát được. Đừng dựa vào một thủ thuật nội bộ của một phiên bản HashMap để coi dữ liệu đã được sửa đúng về mặt nghiệp vụ.

Giải pháp lâu dài nằm ở nơi tạo và sở hữu khóa: giới hạn sửa các trường nhận diện, sao chép dữ liệu thành phần khi cần và kiểm tra các đường làm lộ tham chiếu có thể sửa.

### Đọc dùng chung một trạng thái không đổi

Có thể chia sẻ dữ liệu để chỉ đọc khi trạng thái đã xây dựng hoàn chỉnh, được công bố qua cơ chế bảo đảm nhìn thấy phù hợp và không tiếp tục bị sửa trái hợp đồng. Khóa và giá trị cũng cần ổn định theo mức mà các bên đọc giả định.

Điều kiện này khác với việc “không ai sửa trong lần kiểm thử vừa rồi”. Một tham chiếu Map bị làm lộ và được sửa từ một đường không kiểm soát sẽ phá giả định chỉ đọc.

## 11. Bảng nhận diện lỗi nhanh

| Triệu chứng hoặc cách viết | Cần kiểm tra |
| --- | --- |
| Size còn nhưng get bằng khóa cũ trả null | Dữ liệu equals/hashCode của khóa có bị sửa không? Giá trị có thể null không? |
| Đổi sang ConcurrentHashMap mà khóa vẫn tra sai | Khóa có còn ổn định không, hay chỉ lớp chứa được thay? |
| Khai báo final nhưng dữ liệu khóa đổi | Final đang bảo vệ tham chiếu hay thật sự bảo vệ trạng thái bên trong? |
| Record có thành phần List rồi tra cứu lỗi | Danh sách hoặc phần tử có bị sửa qua tham chiếu khác không? |
| Hai lần tăng nhưng chỉ tăng một | Phạm vi khóa có bao trọn đọc–tính–ghi không? |
| Mỗi phương thức đều synchronized nhưng vẫn sai nghiệp vụ | Những lời gọi cần nguyên tử có bị tách thành nhiều vùng không? |
| Có synchronized ở cả hai nơi nhưng vẫn không phối hợp | Hai bên có dùng cùng monitor và cùng quy tắc dữ liệu không? |
| SynchronizedMap nhưng duyệt bất ngờ | Lượt duyệt có được bảo vệ trên chính Map lớp bọc theo hợp đồng không? |
| Compute trên HashMap được xem là tự an toàn luồng | Đang dựa vào hợp đồng lớp nào? |
| ConcurrentHashMap chứa ArrayList được sửa trực tiếp | Cơ chế bảo vệ danh sách giá trị là gì? |
| Không gặp ConcurrentModificationException | Không đủ thông tin để kết luận an toàn |
| Sao chép Map để sửa lỗi khóa | Bản sao có còn dùng chung khóa đã bị thay đổi không? |

Các câu hỏi này giúp phân loại lỗi trước khi chọn cách sửa. Không phải mọi kết quả null đều do đồng thời, và không phải mọi vấn đề nhiều luồng đều do khóa khả biến.

## 12. Bài tập và lời giải

### Bài 1 — final có đủ không?

Một biến final trỏ tới MutableKey có setter id. Sau khi put, gọi setter. Biến không được gán lại, vậy tra cứu có chắc còn hợp lệ không?

**Lời giải:** không. Final chỉ ngăn đổi tham chiếu biến. Đối tượng vẫn bị sửa dữ liệu nhận diện, có thể vi phạm điều kiện sử dụng khóa trong Map.

### Bài 2 — Đổi mô tả có làm hỏng khóa không?

Khóa có id bất biến và description có thể sửa. Equals/hashCode chỉ xét id. Việc thay description có nhất thiết phá tra cứu băm không?

**Lời giải:** không nhất thiết, vì dữ liệu nhận diện không đổi. Tuy nhiên, nếu description được đọc và sửa giữa các luồng thì cần hợp đồng truy cập riêng cho trường đó.

### Bài 3 — Record chứa danh sách

`record Key(List<String> parts)` nhận một ArrayList từ bên ngoài. Bên ngoài sửa ArrayList sau khi Key được put. Vì sao từ khóa record chưa đủ?

**Lời giải:** record không tự sao chép sâu các đối tượng thành phần. Nội dung danh sách tham gia so bằng và mã băm có thể đổi. Có thể lấy bản sao danh sách không cho sửa khi xây khóa; với phần tử có thể sửa còn cần xử lý sâu hơn.

### Bài 4 — ConcurrentHashMap sửa được khóa khả biến không?

Thay HashMap bằng ConcurrentHashMap nhưng vẫn sửa id dùng trong equals/hashCode sau put. Vấn đề đã được giải quyết chưa?

**Lời giải:** chưa. An toàn cập nhật cấu trúc đồng thời không tự duy trì lại vị trí của một khóa đã thay danh tính. Vẫn cần khóa ổn định.

### Bài 5 — Vì sao ví dụ tách vùng khóa luôn cho 1?

Trong chương trình, mọi get và put đều dùng cùng lock, nhưng kết quả vẫn là 1 sau hai tác vụ. Latch có vai trò gì?

**Lời giải:** latch buộc cả hai đọc trước khi ai được ghi, nên cả hai tính từ 0 và đều ghi 1. Lock ngăn hai truy cập Map diễn ra cùng lúc, nhưng không bảo vệ khoảng đọc–tính–ghi như một đơn vị. Đây là lỗi phạm vi nguyên tử.

### Bài 6 — Mỗi bên một lock

Luồng A synchronized(lockA), luồng B synchronized(lockB), cả hai sửa cùng HashMap. Có thể coi Map đã được bảo vệ vì ở đâu cũng có synchronized không?

**Lời giải:** không. Hai monitor khác nhau không loại trừ nhau. Cần một hợp đồng chung cho dữ liệu chia sẻ và phạm vi thao tác cần bảo vệ.

### Bài 7 — Duyệt synchronizedMap

Có synchronizedMap m, muốn duyệt m.keySet(). Khóa trên đối tượng keySet có thay được khóa trên m theo hợp đồng lớp bọc không?

**Lời giải:** không. Cần bảo vệ lượt duyệt theo monitor của Map được trả về, như synchronized(m), và bảo đảm không có đường truy cập Map nền bỏ qua lớp bọc.

### Bài 8 — Không có ngoại lệ

Một phép thử nhiều luồng với HashMap chạy hàng trăm lần mà không ném ConcurrentModificationException. Có đủ để kết luận đúng không?

**Lời giải:** không. Ngoại lệ chỉ là cơ chế bắt một số vi phạm; mất cập nhật và vấn đề nhìn thấy dữ liệu có thể không làm nó xuất hiện. Phải kiểm tra hợp đồng truy cập và tính nguyên tử, không chỉ chờ lỗi biểu hiện.

### Bài 9 — Map an toàn, giá trị có an toàn không?

ConcurrentHashMap chứa một ArrayList. Hai luồng lấy cùng danh sách rồi cùng add. Tính an toàn của Map đã bao trọn việc này chưa?

**Lời giải:** chưa. Add là thao tác trên đối tượng giá trị. Cần một kiểu giá trị hoặc cơ chế bảo vệ phù hợp cho danh sách, hay một thiết kế cập nhật bằng giá trị mới.

### Bài 10 — Chuyển từ khóa cũ sang khóa mới

Cần đổi định danh, muốn xóa oldKey rồi put newKey trên ConcurrentHashMap. Hai lời gọi có tự là một giao dịch để người đọc không thấy trạng thái giữa chừng không?

**Lời giải:** không. Cần quy định tính nhất quán nhiều bước và cơ chế phù hợp. Nên dùng các đối tượng khóa bất biến, kiểm tra xung đột khóa mới và chính sách thất bại, thay vì sửa chính đối tượng khóa đang nằm trong Map.

## 13. Giữ đúng bốn ranh giới

Trước khi sửa một lỗi HashMap, xác định dữ liệu nhận diện khóa có ổn định không, cấu trúc Map được truy cập theo cơ chế nào, thao tác nghiệp vụ cần nguyên tử tới đâu và giá trị bên trong có bị sửa riêng không.

Ví dụ khóa khả biến giải thích vì sao đúng cùng một tham chiếu vẫn có thể không tra được. Ví dụ bộ đếm giải thích vì sao những lời gọi riêng được bảo vệ vẫn có thể ghép thành một thao tác sai. Hai cách sửa phải nhắm đúng hai nguyên nhân đó.

Khóa ổn định, quyền sở hữu rõ và một hợp đồng cập nhật nhất quán giúp HashMap được dùng đúng. Một lớp chứa dữ liệu không thể tự thay thế cho toàn bộ các quyết định này.

