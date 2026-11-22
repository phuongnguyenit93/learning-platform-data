# Vì sao thứ tự duyệt quan sát được không phải hợp đồng

## 1. Nhìn thấy một thứ tự chưa có nghĩa được quyền dựa vào nó

Khi in một HashMap nhỏ, bạn có thể thấy các khóa hiện ra theo thứ tự rất quen: đúng thứ tự tăng dần, giống thứ tự chèn hoặc lặp lại y hệt qua nhiều lần chạy. Từ đó rất dễ viết thêm mã giả định phần tử được duyệt đầu tiên là phần tử đã thêm đầu tiên.

Điều quan sát là một kết quả thật của lần chạy. Nhưng một kết quả lặp lại chưa tự trở thành lời hứa của API.

HashMap không bảo đảm một thứ tự duyệt cụ thể, cũng không bảo đảm thứ tự đó luôn giữ nguyên theo thời gian. Mã ứng dụng cần đúng với mọi thứ tự mà hợp đồng cho phép, chứ không chỉ với thứ tự tình cờ thấy trong bộ dữ liệu thử. [Tài liệu HashMap, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).

Ví dụ yêu cầu “chọn hồ sơ nhập sớm nhất” không được giải bằng cách lấy phần tử đầu của `map.entrySet()` nếu map là HashMap và thời điểm nhập không được lưu riêng. Tương tự, xuất một báo cáo có thứ tự cố định cần một quy tắc sắp hoặc một cấu trúc giữ đúng thứ tự đó.

Bài học này giải thích vì sao thứ tự trông ổn định, cách tự tạo một phản ví dụ, và cách thiết kế việc duyệt cùng kiểm thử theo đúng yêu cầu.

## 2. Ba mức thông tin: quan sát, triển khai và hợp đồng

| Mức thông tin | Ví dụ | Có thể dùng để làm gì? |
| --- | --- | --- |
| Quan sát trong một lần chạy | “Tôi thấy [0, 16, 1]” | Ghi nhận dữ liệu thực nghiệm |
| Giải thích theo triển khai | “Các khóa này ở những bucket này trong OpenJDK đang xét” | Hiểu vì sao quan sát xuất hiện |
| Bảo đảm công khai của API | “Loại Map này duyệt theo thứ tự chèn” | Thiết kế hành vi cần đúng và kiểm thử theo hợp đồng |

Một giải thích nội bộ chính xác vẫn không tự nâng cấp thành bảo đảm công khai. Bạn có thể đọc mã nguồn một phiên bản, dự đoán đúng thứ tự của một dữ liệu và vẫn không có quyền yêu cầu mọi phiên bản HashMap tương lai giữ thứ tự đó.

Ngược lại, một bảo đảm thứ tự công khai là điều có thể đưa vào hợp đồng ứng dụng khi đã chọn đúng loại cấu trúc và cách cấu hình.

### “Không quy định” không đồng nghĩa “ngẫu nhiên mỗi lần”

HashMap không có nghĩa vụ xáo thứ tự trong mỗi lần duyệt hoặc mỗi lần chạy. Nếu đầu vào, lịch sử cập nhật và triển khai không đổi, việc thường thấy một thứ tự giống nhau hoàn toàn không mâu thuẫn với việc API không bảo đảm thứ tự.

Đừng kiểm thử bằng cách yêu cầu hai lần duyệt HashMap phải khác nhau để chứng minh nó không có hợp đồng thứ tự. Hai lần có thể giống nhau. Đừng yêu cầu chúng phải giống nhau chỉ vì đã quan sát nhiều lần như thế.

Điểm cần nhớ là tính không được bảo đảm, không phải một thuật toán bắt buộc tạo ngẫu nhiên.

## 3. Vì sao HashMap nhỏ đôi khi trông như đã sắp xếp?

HashMap tổ chức các ánh xạ để tra theo khóa thông qua mã băm và bucket. Thứ tự duyệt quan sát được chịu ảnh hưởng của cách triển khai đi qua bảng và các nút trong bucket, không phải một quy tắc công khai “sắp theo khóa” hay “nhớ thứ tự chèn”.

Trong OpenJDK 17, iterator đi qua các vị trí của bảng và các nút mà nó gặp. Điều đó có thể làm một tập khóa số nguyên nhỏ hiện ra theo một mẫu dễ đoán. [Mã nguồn HashMap, OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/HashMap.java).

Giả sử thêm các khóa theo thứ tự:

~~~text
0, 16, 1
~~~

Trong mô hình của ví dụ ở dung lượng 16, 0 và 16 cùng được phân tới một bucket, còn 1 ở một bucket khác. Với dung lượng lớn hơn, 16 có thể nằm ở vị trí tách khỏi 0. Đường duyệt bảng lúc đó có thể cho một thứ tự khác.

Vì thế, cùng ba ánh xạ nhưng hai cấu hình dung lượng ban đầu có thể tạo ra:

~~~text
Một lần quan sát ở Map thứ nhất: [0, 16, 1]
Một lần quan sát ở Map thứ hai: [0, 1, 16]
~~~

Thứ tự thứ hai giống tăng dần không chứng minh HashMap là một bản đồ sắp xếp. Nó là kết quả của dữ liệu và cấu trúc bảng đang xét. Thứ tự thứ nhất cũng không chứng minh HashMap giữ thứ tự chèn nói chung; đó chỉ là sự trùng hợp với lịch sử thêm của ví dụ.

Những yếu tố có thể ảnh hưởng một quan sát gồm dung lượng, cách xử lý va chạm, các lần tăng bảng, lịch sử thêm/xóa và chi tiết phiên bản triển khai. Không cần mọi yếu tố đều thay đổi thứ tự ở mọi trường hợp; chỉ cần API không hứa thứ tự thì mã không được phụ thuộc nó.

### Thêm rồi xóa cũng có thể để lại một lịch sử khác

Hai Map có cùng ánh xạ hiện tại không nhất thiết có cùng cấu trúc bên trong. Một Map từng lớn lên rồi được xóa bớt có thể còn một bảng khác với Map vừa được tạo nhỏ.

Đây là lý do một bộ kiểm thử chỉ tạo Map mới với vài phần tử không đại diện đầy đủ cho một Map đã sống lâu trong ứng dụng.

Không dùng sự khác nhau quan sát được sau một lịch cập nhật như một điều bắt buộc mọi HashMap phải thể hiện. Mục đích là thấy có những thay đổi được phép mà không làm sai ngữ nghĩa của Map.

## 4. Hai Map bằng nhau vẫn có thể duyệt khác nhau

Map mô tả quan hệ khóa–giá trị. Theo hợp đồng equals thông thường của Map, hai Map bằng nhau khi chúng biểu diễn cùng các ánh xạ, không cần cùng thứ tự duyệt. [Hợp đồng Map.equals, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#equals(java.lang.Object)).

Ví dụ hai Map đều có:

~~~text
0  -> zero
16 -> sixteen
1  -> one
~~~

Một lần duyệt cho `[0, 16, 1]`, lần kia cho `[0, 1, 16]`. Vẫn có thể có:

~~~java
first.equals(second) == true
~~~

Trong khi:

~~~java
new ArrayList<>(first.keySet())
        .equals(new ArrayList<>(second.keySet())) == false
~~~

Hai câu đang so những đối tượng có hợp đồng khác nhau:

- So Map: hỏi cùng ánh xạ không.
- So List: hỏi cùng các phần tử ở cùng vị trí không.

Việc chuyển sang List đã đưa thứ tự quan sát vào dữ liệu được đem so. Nó không chứng minh một trong hai Map chứa sai ánh xạ.

Nếu cần kiểm tra kết quả tính toán không có yêu cầu thứ tự, so Map trực tiếp thường phù hợp hơn so chuỗi `toString()` hoặc so List được tạo từ một lượt duyệt bất kỳ.

Nếu có yêu cầu thứ tự, phải kiểm tra yêu cầu đó riêng, sau khi đã chọn cách tạo thứ tự theo hợp đồng.

## 5. Chương trình Java 17+ để tự quan sát

Chương trình dùng khóa Integer khác null và các giá trị chuỗi đơn giản. Nó tạo hai HashMap với cùng lịch thêm ba ánh xạ nhưng dung lượng yêu cầu khác nhau, sau đó tạo một lịch tăng rồi xóa trên một Map.

Phần có nhãn `observed` ghi **thứ tự quan sát trong lần chạy**. Các dòng đó có thể khác ở một triển khai hoặc phiên bản khác mà chương trình vẫn dùng HashMap đúng hợp đồng.

Các phép `check` không yêu cầu một thứ tự cụ thể của HashMap. Chúng chỉ kiểm tra ánh xạ và những thứ tự đã được thiết lập rõ bằng LinkedHashMap, TreeMap hoặc sorted.

Lưu thành `HashMapOrderDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

public class HashMapOrderDemo {
    static void seed(Map<Integer, String> map) {
        map.put(0, "zero");
        map.put(16, "sixteen");
        map.put(1, "one");
    }

    static List<Integer> observedKeys(Map<Integer, String> map) {
        return new ArrayList<>(map.keySet());
    }

    static List<String> sortedReport(Map<Integer, String> source) {
        Map<Integer, String> sorted = new TreeMap<>(source);
        List<String> result = new ArrayList<>();
        for (Map.Entry<Integer, String> entry : sorted.entrySet()) {
            result.add(entry.getKey() + "=" + entry.getValue());
        }
        return result;
    }

    static List<Integer> observedOriginalKeys(Map<Integer, String> map) {
        Set<Integer> original = Set.of(0, 16, 1);
        List<Integer> result = new ArrayList<>();
        for (Integer key : map.keySet()) {
            if (original.contains(key)) {
                result.add(key);
            }
        }
        return result;
    }

    static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Wrong mapping or explicit order");
        }
    }

    public static void main(String[] args) {
        Map<Integer, String> small = new HashMap<>(16);
        Map<Integer, String> large = new HashMap<>(64);
        seed(small);
        seed(large);

        List<Integer> observedSmall = observedKeys(small);
        List<Integer> observedLarge = observedKeys(large);
        System.out.println("observed small=" + observedSmall);
        System.out.println("observed large=" + observedLarge);
        System.out.println("same mappings=" + small.equals(large));
        System.out.println("same observed list="
                + observedSmall.equals(observedLarge));
        System.out.println("sorted small=" + sortedReport(small));
        System.out.println("sorted large=" + sortedReport(large));

        List<Integer> captured = List.copyOf(observedSmall);
        for (int key = 2; key <= 11; key++) {
            small.put(key, "extra-" + key);
        }
        System.out.println("observed original keys after growth="
                + observedOriginalKeys(small));
        for (int key = 2; key <= 11; key++) {
            small.remove(key);
        }
        System.out.println("same mappings after removing extras="
                + small.equals(large));
        System.out.println("captured earlier list=" + captured);
        System.out.println("fresh observed list=" + observedKeys(small));

        Map<Integer, String> linked = new LinkedHashMap<>();
        seed(linked);
        System.out.println("linked insertion order=" + observedKeys(linked));
        linked.put(16, "updated-sixteen");
        System.out.println("linked after existing put=" + observedKeys(linked));
        linked.remove(0);
        linked.put(0, "reinserted-zero");
        System.out.println("linked after remove and put=" + observedKeys(linked));

        Map<Integer, String> linkedCopy = new LinkedHashMap<>(large);
        System.out.println("linked copy of large=" + observedKeys(linkedCopy));
        Map<Integer, String> tree = new TreeMap<>(large);
        System.out.println("tree key order=" + observedKeys(tree));

        List<Integer> sortedKeys = small.keySet().stream().sorted().toList();
        System.out.println("explicit sorted stream=" + sortedKeys);
        Map<Integer, String> expected = Map.of(
                0, "zero", 16, "sixteen", 1, "one");
        check(small.equals(expected));
        check(large.equals(expected));
        check(sortedReport(small).equals(sortedReport(large)));
        check(observedKeys(linked).equals(List.of(16, 1, 0)));
        check(observedKeys(tree).equals(List.of(0, 1, 16)));
        check(sortedKeys.equals(List.of(0, 1, 16)));
        System.out.println("contract checks=PASS");
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 -encoding UTF-8 HashMapOrderDemo.java
java HashMapOrderDemo
~~~

Dùng JDK 17 hoặc mới hơn hỗ trợ phiên bản đích 17. Mã dùng cú pháp và API tương thích Java 17.

Stdout chính xác của lần chạy kiểm chứng:

~~~text
observed small=[0, 16, 1]
observed large=[0, 1, 16]
same mappings=true
same observed list=false
sorted small=[0=zero, 1=one, 16=sixteen]
sorted large=[0=zero, 1=one, 16=sixteen]
observed original keys after growth=[0, 1, 16]
same mappings after removing extras=true
captured earlier list=[0, 16, 1]
fresh observed list=[0, 1, 16]
linked insertion order=[0, 16, 1]
linked after existing put=[0, 16, 1]
linked after remove and put=[16, 1, 0]
linked copy of large=[0, 1, 16]
tree key order=[0, 1, 16]
explicit sorted stream=[0, 1, 16]
contract checks=PASS
~~~

Không biến các dòng quan sát HashMap thành chuỗi bắt buộc cho mọi máy. Ý nghĩa của bài chính là phân biệt bản ghi thực nghiệm này với bảo đảm API. Dòng `contract checks=PASS` dựa vào các yêu cầu hợp đồng được viết trong check, không dựa vào việc hai dòng observed đầu phải khác nhau.

### Các kết quả cần đối chiếu

`same mappings=true` và `same observed list=false` cùng xuất hiện, minh chứng khác nhau về thứ tự không làm mất tính bằng nhau của ánh xạ.

Hai dòng `sorted` giống nhau vì hàm báo cáo dùng TreeMap với thứ tự khóa tự nhiên. Thứ tự đã trở thành một bước xử lý có chủ đích, không phải đoán theo HashMap.

Sau khi thêm các khóa phụ rồi xóa chúng, Map nhỏ lại có cùng ánh xạ như Map lớn. Trong lần chạy, danh sách khóa mới quan sát khác danh sách đã chụp trước đó. Việc Map quay lại cùng dữ liệu không làm lịch sử cấu trúc tự quay ngược.

Danh sách `captured` vẫn giữ những phần tử và thứ tự đã chụp. Nó là một List riêng; việc giữ một quan sát trong một List không làm HashMap nguồn phải duyệt theo List đó về sau.

Các dòng LinkedHashMap, TreeMap và sorted stream có ý nghĩa khác: thứ tự của chúng đến từ những cơ chế được chọn rõ ràng. Chúng sẽ được dùng để thiết kế hành vi ổn định ở phần sau.

## 6. Khi cần thứ tự, chọn đúng loại bảo đảm

### Giữ thứ tự chèn bằng LinkedHashMap mặc định

Nếu thứ tự người dùng hoặc nguồn dữ liệu đưa vào là một phần của yêu cầu, có thể dùng:

~~~java
Map<Integer, String> map = new LinkedHashMap<>();
map.put(0, "zero");
map.put(16, "sixteen");
map.put(1, "one");
~~~

LinkedHashMap mặc định có thứ tự duyệt theo thứ tự chèn của các khóa. Việc put lại một khóa đang tồn tại thay giá trị mà không tự đưa khóa đó xuống cuối. Xóa khóa rồi thêm lại tạo một lần chèn mới, nên khóa xuất hiện ở vị trí chèn mới. [Tài liệu LinkedHashMap, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).

Trong chương trình:

~~~text
Chèn 0, 16, 1: [0, 16, 1]
Put lại 16:    [0, 16, 1]
Xóa rồi thêm 0:[16, 1, 0]
~~~

Đây là các thao tác tuần tự trên LinkedHashMap mặc định. Loại này còn có chế độ thứ tự truy cập được chọn bằng constructor khác; chế độ đó có quy tắc riêng và không nên được gọi chung là “luôn giữ thứ tự chèn”.

### Sắp theo khóa bằng TreeMap

Nếu yêu cầu là luôn duyệt theo khóa tăng dần hoặc theo Comparator được định nghĩa:

~~~java
Map<Integer, String> sorted = new TreeMap<>(source);
~~~

Với các khóa Integer khác null trong ví dụ, TreeMap sắp theo thứ tự số tự nhiên, nên kết quả là 0, 1, 16. Thứ tự này độc lập với thứ tự đưa ba khóa vào.

TreeMap cung cấp thứ tự theo thứ tự tự nhiên của khóa hoặc Comparator đã chọn. Nó không tự sắp theo giá trị và không đồng nghĩa với thứ tự chèn. [Tài liệu TreeMap, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html).

Khi dùng khóa hoặc Comparator khác, cần bảo đảm các khóa so được với nhau và quan hệ so sánh phù hợp với ý nghĩa khóa. Không thay HashMap bằng TreeMap với một comparator coi các khóa khác nhau là đồng hạng rồi mặc định mọi ánh xạ sẽ giữ nguyên.

TreeMap với thứ tự tự nhiên cũng không phải lựa chọn sao chép mọi HashMap có khóa null mà không cần điều chỉnh. Ví dụ đầy đủ cố ý dùng các khóa Integer khác null để tập trung vào thứ tự.

### Giữ HashMap để tra, sắp lúc xuất

Nếu chủ yếu cần tra nhanh nhưng chỉ cần một báo cáo có thứ tự ở ranh giới xuất dữ liệu, có thể giữ HashMap rồi tạo kết quả đã sắp:

~~~java
List<Integer> keys = map.keySet().stream()
        .sorted()
        .toList();
~~~

Chỉ List kết quả được tạo theo thứ tự tăng của các khóa. Map nguồn không bị biến thành một Map sắp xếp. Nếu cần cả cặp, dùng cách tạo báo cáo từ các cặp phù hợp hoặc một Map đã sắp như hàm `sortedReport` trong chương trình.

Việc sắp có chi phí theo số phần tử và bộ nhớ kết quả. Đó là một phần công việc cần tính khi yêu cầu thật sự đòi một trình tự ổn định.


## 7. Sao chép có thể giữ một quan sát mà không phục hồi lịch sử

### new LinkedHashMap<>(hashMap) giữ thứ tự nào?

Xét:

~~~java
Map<Integer, String> copy = new LinkedHashMap<>(hashMap);
~~~

LinkedHashMap mới nhận các ánh xạ theo thứ tự nguồn được duyệt trong lúc sao chép. Sau đó, bản đồ mới giữ thứ tự chèn của chính nó.

Điều đó không khôi phục thứ tự người dùng đã chèn vào HashMap trước kia. Nếu HashMap đã bỏ thông tin thứ tự đó khỏi hợp đồng dữ liệu của bạn, một thao tác sao chép về sau không tự suy ra lại lịch sử.

Trong chương trình, seed thêm 0, 16, 1, nhưng Map large được quan sát theo 0, 1, 16. Sao chép large sang LinkedHashMap cho 0, 1, 16 trong lần chạy. Đây là thứ tự LinkedHashMap mới đã nhận, không phải lịch sử seed đã được phục hồi.

Nếu cần thứ tự nhập ban đầu, giữ nó ngay từ nơi tiếp nhận: dùng một cấu trúc có thứ tự phù hợp hoặc lưu thông tin vị trí/thời điểm cần dùng. Đừng đi qua một HashMap rồi trông chờ có thể dựng lại một thứ tự chưa được lưu.

### List chụp lại một lần duyệt

~~~java
List<Integer> snapshot = new ArrayList<>(hashMap.keySet());
~~~

List có vị trí phần tử cụ thể. Những lần duyệt List đó sẽ theo các vị trí đã lưu, miễn là chính List không bị sửa.

Nhưng việc tạo List mới từ HashMap ở một thời điểm khác có thể cho một quan sát khác. “Bản chụp này có thứ tự” khác với “nguồn có một thứ tự được bảo đảm”.

`List.copyOf` trong chương trình dùng các khóa khác null và tạo một List không cho sửa cấu trúc. Nó giữ các phần tử cùng thứ tự từ danh sách quan sát được truyền vào, không ràng buộc HashMap phải phát lại thứ tự đó về sau.

### Map.copyOf và chỉ đọc không đồng nghĩa giữ thứ tự

Một Map không cho cập nhật vẫn cần được xem hợp đồng thứ tự riêng. Không lấy thuộc tính “không sửa được” làm bằng chứng rằng nó giữ thứ tự chèn của nguồn.

Tương tự, bọc một Map thành giao diện chỉ đọc có thể giữ lại khả năng nhìn dữ liệu nguồn nhưng không tự tạo một thứ tự mà nguồn không hứa. Thứ tự, khả năng sửa đổi và sự độc lập với nguồn là các thuộc tính cần lựa chọn riêng.

| Kết quả cần có | Cần quyết định |
| --- | --- |
| Không được sửa qua đối tượng trả về | Chọn lớp bọc hoặc kiểu kết quả phù hợp |
| Không đổi ánh xạ khi nguồn đổi | Chọn một bản sao phù hợp |
| Có một thứ tự hiển thị ổn định | Chọn quy tắc thứ tự rõ ràng |
| Giữ đúng lịch sử nhập | Lưu lịch sử hoặc dùng cấu trúc giữ lịch sử ngay từ đầu |

Một cách tạo dữ liệu có thể đáp ứng một hàng nhưng không đáp ứng các hàng khác. Đó là lý do tên biến readOnly hoặc snapshot chưa đủ để mô tả hợp đồng.

## 8. Stream không tự biến thứ tự quan sát thành thứ tự nghiệp vụ

### forEach và forEachOrdered

`forEachOrdered` thực hiện hành động theo thứ tự gặp phần tử nếu stream có một thứ tự gặp được xác định. Từ “Ordered” không có nghĩa tự sắp khóa và cũng không có nghĩa tự suy ra lịch sử chèn của một HashMap. [Tài liệu Stream.forEachOrdered, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#forEachOrdered(java.util.function.Consumer)).

Do đó:

~~~java
hashMap.keySet().stream().forEachOrdered(System.out::println);
~~~

không phải cách yêu cầu HashMap phải xuất khóa theo thứ tự chèn hay thứ tự tăng dần. Nó chưa nêu quy tắc nghiệp vụ nào để tạo ra thứ tự đó.

Nếu cần khóa tăng dần, phải tạo thứ tự rõ:

~~~java
hashMap.keySet().stream()
        .sorted()
        .forEachOrdered(System.out::println);
~~~

Ví dụ giả sử các khóa so được theo thứ tự tự nhiên và không có null không được comparator hỗ trợ. Cách viết sorted đã thêm một quy tắc mà nguồn HashMap không có.

Với xử lý song song, `forEach` cũng không phải lựa chọn để yêu cầu hiệu ứng in ra bám theo một thứ tự nguồn đã chọn. Cần phân biệt thứ tự của dữ liệu kết quả với cách các tác vụ được thực thi.

### findFirst và limit không phải “sớm nhất” hay “nhỏ nhất”

Một phần tử do HashMap duyệt trước không mặc nhiên là:

- Khóa nhỏ nhất.
- Ánh xạ được thêm đầu tiên.
- Bản ghi có thời gian sớm nhất.
- Mục có độ ưu tiên cao nhất.

`findFirst` hoặc `limit` trên một nguồn không có quy tắc thứ tự cần thiết không thể tự cung cấp các ý nghĩa đó. Nếu cần phần tử có thời gian sớm nhất, hãy so trường thời gian; nếu cần khóa nhỏ nhất, hãy tính theo thứ tự khóa hoặc dùng cấu trúc có hợp đồng phù hợp.

### Sắp theo một tiêu chí nhưng còn đồng hạng

Giả sử báo cáo phải xếp theo điểm giảm. Hai mục cùng điểm 90 vẫn chưa có thứ tự tương đối được quyết định chỉ từ điểm.

Nếu yêu cầu đầu ra phải tái lập hoàn toàn, bổ sung tiêu chí phụ, chẳng hạn mã mục tăng dần. Một thuật toán sắp ổn định có thể giữ thứ tự đầu vào giữa các phần tử đồng hạng; nếu đầu vào lấy từ HashMap với thứ tự chưa được bảo đảm thì cách đó vẫn chưa tạo một thứ tự nghiệp vụ đầy đủ.

Trong chương trình, các khóa Integer là phân biệt và sorted theo khóa tự nhiên, nên không có sự mơ hồ tương tự giữa hai khóa khác nhau. Với kiểu khóa hoặc comparator khác, cần xem lại tính đầy đủ của quy tắc so sánh.

## 9. Kiểm thử đúng ngữ nghĩa

### Không có yêu cầu thứ tự: so ánh xạ

Với một hàm trả Map, nếu yêu cầu là trả đúng các cặp dữ liệu, có thể kiểm tra:

~~~java
Map<Integer, String> expected = Map.of(
        0, "zero",
        16, "sixteen",
        1, "one");

if (!actual.equals(expected)) {
    throw new AssertionError("Wrong mappings");
}
~~~

Đây là đoạn minh họa đặt trong một ngữ cảnh đã có actual. Không dùng thứ tự đối số của Map.of như một cách yêu cầu thứ tự duyệt của expected.

So riêng một tập giá trị có thể chưa đủ: hai khóa bị gắn nhầm giá trị vẫn có thể tạo cùng tập giá trị. So Map giữ được việc kiểm tra đúng quan hệ khóa–giá trị.

Cũng không so `actual.toString()` với một chuỗi được viết theo thứ tự bạn tình cờ quan sát. Nếu chuỗi chỉ được dùng để kiểm tra dữ liệu Map, phép kiểm tra đó đã đưa vào một yêu cầu ngoài hợp đồng.

### Có yêu cầu thứ tự: kiểm tra sau khi đã tạo đúng thứ tự

Nếu hàm trả một báo cáo theo khóa tăng dần, kiểm tra List kết quả theo vị trí là hợp lý:

~~~java
List<Integer> expectedOrder = List.of(0, 1, 16);
if (!sortedKeys.equals(expectedOrder)) {
    throw new AssertionError("Wrong key order");
}
~~~

Lúc này cần chỉ ra sortedKeys được tạo bằng quy tắc nào, như sorted hoặc TreeMap. Không sửa phép kiểm thử để bỏ qua thứ tự nếu chính yêu cầu sản phẩm cần một thứ tự rõ ràng.

Với một chức năng giữ thứ tự nhập, kiểm tra chuỗi sự kiện nhập cùng cấu trúc giữ thứ tự đó. Nếu dữ liệu đi qua một nguồn không có thứ tự, hãy quyết định nơi nào cần áp dụng quy tắc, thay vì đổ lỗi cho HashMap.

### Dùng dữ liệu giúp lộ giả định ngầm

Những bộ nhỏ gồm các khóa 1, 2, 3 rất dễ che lỗi “HashMap tự sắp tăng”. Một phép rà soát có giá trị nên có cả khóa chia sẻ bucket ở một cấu hình, lịch chèn khác nhau hoặc nguồn từng tăng rồi xóa.

Điều cần khẳng định là kết quả của thuật toán vẫn đúng với những lịch đó. Không cần khẳng định rằng mọi cặp lịch thử phải tạo thứ tự duyệt khác nhau, vì sự khác nhau cũng không phải điều HashMap bắt buộc cung cấp.

Chương trình đầy đủ tuân theo nguyên tắc này: nó in quan sát nhưng các check chức năng không đòi hai HashMap phải khác thứ tự.

### Kiểm thử không sửa được một hợp đồng bị bỏ trống

Một trăm lần chạy thành công có thể giúp phát hiện một số lỗi, nhưng không biến hành vi chưa được API bảo đảm thành điều được bảo đảm. Khi một tính năng thật sự phụ thuộc thứ tự, phải thể hiện quyết định đó trong cấu trúc hoặc thuật toán của tính năng.

Cố định phiên bản JDK giúp tái lập môi trường, nhưng vẫn nên phân biệt một phụ thuộc có chủ đích vào triển khai với một hợp đồng thư viện công khai. Nếu có phụ thuộc triển khai phục vụ một thí nghiệm, hãy ghi rõ điều kiện của thí nghiệm.

## 10. Áp dụng tại ranh giới xuất dữ liệu và lựa chọn cấu trúc

### Báo cáo và giao diện

Nếu danh sách cột, danh sách mục hoặc nhóm hiển thị cần theo một thứ tự, hãy nêu rõ “theo mã”, “theo tên”, “theo thời gian” hoặc “theo vị trí nhập”. Những cụm này mới cho biết phải chọn comparator, lưu trường dữ liệu nào hoặc dùng cấu trúc gì.

“Hiện như lúc tôi in Map” không phải một đặc tả đủ bền vững. Đổi dung lượng để tối ưu hiệu năng không nên làm thay đổi trình tự nghiệp vụ của màn hình.

### Văn bản, bộ nhớ đệm và so sánh đầu ra

Hai Map bằng nhau có thể có chuỗi hiển thị khác thứ tự. Nếu đầu ra văn bản được đem so khác biệt từng dòng, dùng làm đầu vào tính mã băm hoặc làm khóa bộ nhớ đệm, thứ tự cần được chuẩn hóa theo một quy tắc được công bố.

Sắp các khóa là một phần của chuẩn hóa, nhưng không tự giải quyết mọi thứ: nếu giá trị chứa Map lồng nhau thì còn thứ tự của lớp bên trong; nếu dùng một định dạng văn bản thì còn quy tắc biểu diễn ký tự và giá trị.

Hàm sortedReport trong ví dụ là một báo cáo dễ đọc cho dữ liệu Integer/String cụ thể, không được giới thiệu như một định dạng mã hóa chuẩn dùng chung. Không lấy phép nối `key + "=" + value` làm một định dạng duy nhất cho mọi dữ liệu có thể chứa dấu phân cách.

### Chi phí và trách nhiệm

| Yêu cầu chính | Hướng xử lý |
| --- | --- |
| Tra theo khóa, kết quả không phụ thuộc thứ tự | HashMap và thuật toán không dựa vào vị trí duyệt |
| Duyệt theo thứ tự chèn | LinkedHashMap mặc định, nhận dữ liệu theo thứ tự cần giữ |
| Duyệt theo khóa | TreeMap với thứ tự tự nhiên hoặc comparator phù hợp |
| Chỉ một số lần xuất cần có thứ tự | Giữ cấu trúc tra cứu, sắp bản kết quả lúc xuất |
| Cần một lịch ưu tiên khác với thứ tự chèn và thứ tự khóa | Lưu thông tin ưu tiên và dùng cấu trúc/thuật toán thể hiện quy tắc đó |

Các lựa chọn có chi phí bộ nhớ và thao tác khác nhau. LinkedHashMap giữ thêm quan hệ thứ tự; TreeMap thực hiện các thao tác theo cấu trúc cây; sắp một bản báo cáo cần công việc tạo kết quả và so sánh. Đổi loại Map nên xuất phát từ yêu cầu, không chỉ để làm một phép kiểm thử chuỗi tình cờ vượt qua.

### Thứ tự không thay thế các bảo đảm khác

Có một thứ tự rõ không tự làm dữ liệu an toàn luồng. Một iterator phát hiện thay đổi không tạo bản chụp nhất quán. Một Map chỉ đọc không tự là bản sao độc lập.

Trong bài, mọi thao tác diễn ra tuần tự và các nguồn được giữ ổn định trong mỗi lượt duyệt. Nếu ứng dụng có cập nhật đồng thời, cần cơ chế đọc/cập nhật phù hợp ngoài quyết định về thứ tự.

## 11. Bài tập và lời giải

### Bài 1 — Cùng thứ tự qua nhiều lần chạy

Bạn thêm 3, 1, 2 vào HashMap và luôn quan sát [1, 2, 3] trên máy hiện tại. Có thể ghi đặc tả hàm trả khóa tăng dần mà không thêm bước xử lý nào không?

**Lời giải:** không. Quan sát có thể phù hợp với cách phân bucket hiện tại nhưng HashMap không có hợp đồng sắp tăng. Muốn hàm cam kết tăng dần, dùng một cấu trúc sắp theo khóa hoặc sắp kết quả rõ ràng.

### Bài 2 — Không bảo đảm có phải luôn đổi không?

Một phép kiểm thử khẳng định hai lần tạo HashMap phải cho hai thứ tự khác nhau vì “HashMap không có thứ tự”. Phép kiểm thử sai ở đâu?

**Lời giải:** không bảo đảm thứ tự không có nghĩa bắt buộc ngẫu nhiên hoặc bắt buộc khác nhau. Hai lần có thể giống nhau. Điều đúng là thuật toán không được cần một thứ tự cụ thể chưa được hợp đồng cung cấp.

### Bài 3 — Map bằng nhau, List khác nhau

Hai Map có cùng cặp dữ liệu nhưng List tạo từ keySet khác thứ tự. Map.equals trả true, List.equals trả false. Có mâu thuẫn không?

**Lời giải:** không. Map so cùng ánh xạ; List so các phần tử theo vị trí. Việc chuyển sang List đã đưa một quan sát thứ tự vào đối tượng đang kiểm tra.

### Bài 4 — Sao chép sang LinkedHashMap

Dữ liệu được chèn vào HashMap theo A, B, C, nhưng một lần duyệt thấy C, A, B. Sao chép sang LinkedHashMap có khôi phục A, B, C không?

**Lời giải:** không. Map mới nhận theo thứ tự đang duyệt được là C, A, B trong lần đó và giữ lịch chèn của chính nó. Muốn giữ A, B, C phải lưu thứ tự ngay từ nguồn hoặc dùng cấu trúc phù hợp từ đầu.

### Bài 5 — Put lại và xóa rồi thêm

LinkedHashMap mặc định đang có A, B, C. Put lại B với giá trị mới cho thứ tự gì? Sau đó xóa A rồi thêm lại A thì sao?

**Lời giải:** put lại B giữ A, B, C. Xóa rồi thêm A cho B, C, A. Đây là hợp đồng của chế độ thứ tự chèn đã chọn, không phải suy luận từ HashMap.

### Bài 6 — forEachOrdered có sắp không?

Có thể thay vòng for-each trên HashMap bằng stream.forEachOrdered để bảo đảm in theo thứ tự chèn không?

**Lời giải:** không. forEachOrdered không tự tạo lịch sử chèn hoặc sắp khóa cho nguồn thiếu bảo đảm đó. Chọn nguồn giữ thứ tự cần có, hoặc tạo quy tắc như sorted trước khi xuất.

### Bài 7 — Chỉ sắp theo điểm

Một báo cáo lấy mục từ HashMap rồi sắp giảm theo điểm. Hai mục cùng điểm nhưng không có tiêu chí phụ. Đã bảo đảm toàn bộ đầu ra luôn có cùng thứ tự chưa?

**Lời giải:** chưa. Thứ tự tương đối của hai mục đồng điểm vẫn có thể dựa vào một thứ tự đầu vào không được bảo đảm. Nếu cần tái lập toàn bộ, thêm tiêu chí phụ phù hợp, chẳng hạn mã tăng.

### Bài 8 — Kiểm thử đúng yêu cầu

Một hàm chỉ được yêu cầu trả đúng Map mã–tên. Phép kiểm thử hiện so toString với một chuỗi viết theo thứ tự chèn. Sửa thế nào? Nếu yêu cầu thật sự là trả một báo cáo theo tên thì sao?

**Lời giải:** trường hợp đầu so Map trực tiếp với các ánh xạ mong đợi, không yêu cầu thứ tự thừa. Trường hợp thứ hai cần thể hiện việc sắp theo tên trong mã tạo báo cáo, quy định cách xử lý đồng tên nếu cần, rồi kiểm tra List hoặc văn bản đầu ra theo đúng thứ tự đó.

Một thứ tự quan sát là dữ liệu thực nghiệm để giải thích triển khai. Một thứ tự dùng làm yêu cầu phải có nguồn bảo đảm rõ: hợp đồng của cấu trúc hoặc một bước xử lý được thiết kế cho mục tiêu đó.

