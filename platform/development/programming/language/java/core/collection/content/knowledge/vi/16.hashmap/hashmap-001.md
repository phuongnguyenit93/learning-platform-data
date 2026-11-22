# Bảng băm, bucket và quy trình tìm khóa

## 1. HashMap giải quyết bài toán tra cứu như thế nào?

Giả sử cần tra tên sản phẩm từ mã sản phẩm. Với một danh sách các cặp, cách đơn giản là đi lần lượt cho tới khi gặp mã phù hợp. Nếu dữ liệu lớn và phải tra nhiều lần, việc luôn bắt đầu từ đầu danh sách sẽ tốn công.

Bảng băm dùng một thông tin tính từ khóa để thu hẹp nơi cần tìm. Thay vì xét tất cả ánh xạ, nó chọn một vùng chứa ứng viên rồi chỉ kiểm tra các khóa trong vùng đó.

Trong `HashMap`, vùng đó thường được gọi là **bucket**: một vị trí trong bảng chứa các ánh xạ cùng được phân vào vị trí ấy. Có thể hình dung bucket như một ngăn lưu hồ sơ, còn mã băm là dữ liệu giúp chọn ngăn. Tới đúng ngăn vẫn phải kiểm tra đúng hồ sơ; số ngăn không thay thế cho danh tính khóa.

`HashMap` là một triển khai Map dựa trên bảng băm. Hiệu quả tra cứu phụ thuộc vào việc các khóa được phân bố phù hợp giữa các bucket. Nó không bảo đảm thứ tự chèn hoặc thứ tự duyệt ổn định. [Tài liệu HashMap, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).

Sau bài học, bạn cần giải thích được đường đi:

~~~text
khóa cần tìm
    -> mã băm từ khóa
    -> mã băm được xử lý nội bộ
    -> chỉ số bucket
    -> kiểm tra ứng viên trong bucket
    -> tìm đúng khóa hoặc kết luận không có.
~~~

Trọng tâm không phải học thuộc một công thức rồi tự tính bucket trong mã ứng dụng. Khi dùng HashMap, ứng dụng vẫn gọi `put`, `get` hoặc `containsKey`; hiểu cơ chế giúp thiết kế khóa đúng và chẩn đoán tra cứu sai.

## 2. Những khái niệm cần tách riêng

| Khái niệm | Ý nghĩa |
| --- | --- |
| Khóa (key) | Đối tượng dùng để xác định ánh xạ muốn tra |
| Giá trị (value) | Dữ liệu gắn với khóa |
| Mã băm (hash code) | Một số nguyên do `hashCode()` của khóa cung cấp |
| Mã băm nội bộ | Số được HashMap xử lý để sử dụng trong bảng |
| Dung lượng bảng (capacity) | Số vị trí bucket của bảng |
| Chỉ số bucket | Vị trí cụ thể được chọn trong bảng |
| Nút (node) | Đơn vị giữ một ánh xạ và thông tin phục vụ tìm kiếm |
| Số ánh xạ (size) | Số cặp khóa–giá trị đang được lưu |

Dung lượng không đồng nghĩa số ánh xạ. Một bảng có 16 bucket có thể mới chứa bốn ánh xạ. Bốn ánh xạ đó có thể nằm ở bốn bucket khác nhau hoặc cùng dồn vào một bucket.

Mã băm cũng không phải chỉ số bucket. `hashCode()` trả một giá trị `int`, còn bảng chỉ có một số hữu hạn vị trí. Cần một bước ánh xạ mã băm vào phạm vi chỉ số hợp lệ.

Trong OpenJDK 17, một nút thông thường giữ mã băm nội bộ đã tính, khóa, giá trị và một liên kết tới nút kế tiếp khi bucket có chuỗi nút. Những bucket được chuyển sang dạng cây dùng một loại nút có thêm thông tin cây. Đây là mô hình triển khai được dùng để giải thích cơ chế, không phải các trường công khai để mã ứng dụng truy cập.

Đừng nhầm HashMap với một mảng có thể truy cập bằng khóa số nguyên. Khóa `Integer.valueOf(100)` không bắt buộc được lưu ở vị trí 100, và HashMap không tạo tự động 101 phần tử chỉ vì có khóa số 100.

## 3. hashCode và equals có trách nhiệm khác nhau

Mã băm giúp chọn và lọc nơi tìm. `equals` giúp xác định hai đối tượng có được coi là cùng khóa theo cách định nghĩa dữ liệu hay không.

Hợp đồng cần giữ:

- Nếu hai đối tượng bằng nhau theo `equals`, chúng phải có cùng `hashCode`.
- Hai đối tượng có cùng mã băm vẫn có thể không bằng nhau.
- Những thông tin ảnh hưởng tới phép so bằng và mã băm cần được dùng nhất quán.

Hợp đồng không yêu cầu mọi đối tượng khác nhau có mã băm khác nhau. Có thể có nhiều khóa khác nhau cùng một mã băm; cấu trúc bảng băm phải xử lý trường hợp này. [Hợp đồng Object.hashCode và Object.equals, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html).

Ví dụ minh họa:

~~~text
Khóa A: hashCode = 1
Khóa C: hashCode = 1
A.equals(C) = false

Kết luận: A và C là hai khóa khác nhau, dù trùng mã băm.
~~~

Ngược lại, một đối tượng mới biểu diễn cùng dữ liệu khóa với đối tượng đã lưu phải được tra được nếu equals/hashCode được cài đúng và thông tin khóa không bị thay đổi.

Không cần cùng tham chiếu đối tượng để tìm cùng một khóa. Phép `==` có thể giúp nhận ra nhanh trường hợp đúng cùng đối tượng, nhưng nó không thay thế cho khái niệm bằng nhau theo dữ liệu.

Mã băm không phải mã định danh duy nhất, không phải thứ tự sắp xếp và không phải giá trị mã hóa bảo mật. Một mã băm bằng 0 cũng không có nghĩa khóa không tồn tại.

## 4. Từ mã băm của khóa tới mã nội bộ trong OpenJDK 17

Phần chi tiết bên dưới được đối chiếu với `HashMap` của OpenJDK 17. Công thức, bố trí nút và các tối ưu có thể thay đổi giữa triển khai hoặc phiên bản; hợp đồng về tra khóa đúng theo equals/hashCode mới là điều mã ứng dụng cần dựa vào. [Mã nguồn HashMap, OpenJDK 17](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/HashMap.java).

Với một khóa khác null, mô hình xử lý mã băm là:

~~~java
int mixed = rawHash ^ (rawHash >>> 16);
~~~

Trong đó:

- `rawHash` là mã do `key.hashCode()` cung cấp.
- `>>> 16` dịch phải không dấu 16 bit, đưa phần bit cao xuống thấp.
- `^` là phép XOR.
- `mixed` là mã được dùng tiếp trong cơ chế bảng.

Vì chỉ số bucket ở dung lượng lũy thừa của hai phụ thuộc một số bit thấp, việc trộn phần bit cao xuống giúp những khác biệt ở bit cao có thể tham gia chọn bucket. Nó không tạo ra một mã duy nhất cho mọi khóa và không sửa được một hàm hashCode luôn trả cùng số cho tất cả đối tượng.

Ví dụ:

~~~text
rawHash = 65536 = 0x00010000
rawHash >>> 16 = 1
mixed = 65536 XOR 1 = 65537 = 0x00010001
~~~

Nếu chỉ xét bốn bit thấp của rawHash thì chúng đều là 0; sau bước trộn, bốn bit thấp có thêm thông tin từ bit cao.

Với khóa null, OpenJDK xử lý mã nội bộ là 0, không gọi `hashCode()` trên null. Điều này giúp HashMap hỗ trợ khóa null nhưng không có nghĩa bucket 0 chỉ dành riêng cho null. Những khóa khác có mã nội bộ đưa về chỉ số 0 vẫn có thể cùng bucket.

Mã băm có thể âm. Đây không phải một tình trạng lỗi; toàn bộ 32 bit của int vẫn có thể tham gia cơ chế chọn vị trí.

## 5. Chọn bucket bằng dung lượng hiện tại

Trong mô hình OpenJDK 17, khi dung lượng bảng n là một lũy thừa của hai, chỉ số được tính bằng:

~~~java
int index = mixedHash & (n - 1);
~~~

Đây là phép AND bit, không phải toán tử logic `&&`. Với n = 16:

~~~text
n - 1 = 15 = 0b1111

mixedHash & 15 giữ lại bốn bit thấp.
Kết quả nằm từ 0 tới 15.
~~~

Ví dụ:

| Mã hashCode ban đầu | Mã sau trộn | Bucket nếu n = 16 | Bucket nếu n = 32 |
| --- | --- | --- | --- |
| 1 | 1 | 1 | 1 |
| 17 | 17 | 1 | 17 |
| 65536 | 65537 | 1 | 1 |
| 2 | 2 | 2 | 2 |
| -1 | -65536 | 0 | 0 |

Hai điểm rút ra từ bảng:

**Cùng bucket không nhất thiết cùng mã băm.** Mã nội bộ 1, 17 và 65537 đều vào bucket 1 khi n = 16.

**Bucket phụ thuộc dung lượng.** Mã 17 ở bucket 1 với n = 16 nhưng chuyển sang bucket 17 khi n = 32. Không thể xem chỉ số bucket là một thuộc tính cố định của khóa.

Với -1, phép dịch không dấu đưa 16 bit 1 xuống thành 65535; XOR cho kết quả -65536. AND với 15 hoặc 31 vẫn cho chỉ số hợp lệ bằng 0. Không cần gọi Math.abs để xử lý số âm trong công thức này.

Không thay công thức trên bằng `Math.abs(hashCode) % n` rồi cho rằng đã mô tả chính xác OpenJDK. Đó là một thuật toán khác, và `Math.abs(Integer.MIN_VALUE)` vẫn là số âm do miền int không chứa đối số dương tương ứng. Khi dùng HashMap thật, hãy để chính triển khai tính vị trí.

Hàm `bucket` trong chương trình chỉ mô phỏng công thức cho các dung lượng 16 và 32 được chọn sẵn. Nó kiểm tra điều kiện lũy thừa của hai và không dùng phản chiếu để đọc bảng riêng tư của đối tượng HashMap.

## 6. Va chạm: tới đúng bucket vẫn chưa tìm đúng khóa

Giả sử bốn khóa được thêm theo thứ tự A, B, C, D:

~~~text
A: rawHash 1      -> mixed 1
B: rawHash 17     -> mixed 17
C: rawHash 1      -> mixed 1
D: rawHash 65536  -> mixed 65537
~~~

Với dung lượng 16, cả bốn cùng vào bucket 1. Một sơ đồ chuỗi nút tương ứng cho ví dụ nhỏ:

~~~text
table[0]  -> rỗng
table[1]  -> [hash=1, A, alpha]
            -> [hash=17, B, beta]
            -> [hash=1, C, gamma]
            -> [hash=65537, D, delta]
table[2]  -> rỗng
...
table[15] -> rỗng
~~~

Sơ đồ diễn giải dạng chuỗi của ví dụ khi đối chiếu triển khai OpenJDK; nó không phải một bản in trực tiếp các trường riêng tư. HashMap không có cam kết API về thứ tự chèn của mọi chuỗi nội bộ hoặc thứ tự duyệt.

Có thể phân biệt hai mức va chạm:

1. Khác mã nội bộ nhưng rơi vào cùng bucket, như A và B.
2. Cùng toàn bộ mã nội bộ nhưng khóa không bằng nhau, như A và C.

Mức thứ nhất có thể loại ứng viên sớm bằng cách so mã nội bộ. Mức thứ hai còn phải phân biệt bằng khóa. Bởi vậy, chỉ số bucket bằng nhau chưa đủ và ngay cả mã băm bằng nhau cũng chưa đủ để kết luận đã tìm được ánh xạ.

HashMap không ghi đè mọi khóa chung bucket. Một ánh xạ chỉ được thay giá trị khi khóa được nhận diện là bằng khóa đã có. Nếu A và C khác nhau theo equals thì chúng cùng tồn tại dù mã băm giống hệt.

## 7. Quy trình get(key) trên một bucket dạng chuỗi

Có thể đọc quy trình theo những bước sau:

1. Xác định bảng; nếu đã có bảng với dung lượng hợp lệ, tính vị trí cần tìm.
2. Lấy nút đầu của bucket được chọn.
3. Nếu bucket rỗng, kết luận không tìm thấy khóa ở đây.
4. Nếu có nút, so mã băm nội bộ lưu trong nút với mã của khóa đang dò.
5. Chỉ khi mã phù hợp mới xét cùng tham chiếu hoặc so bằng khóa.
6. Nếu nút hiện tại chưa khớp, xét các ứng viên tiếp theo trong bucket.
7. Tìm được nút thì trả giá trị của nó; hết ứng viên mà không khớp thì trả null.

Cách kiểm tra khóa trong một nút có hai đường chính:

~~~text
mã nội bộ trùng
    và
    (khóa lưu cùng tham chiếu với khóa dò
     hoặc khóa dò khác null và equals với khóa lưu)
~~~

Đó là mô hình logic, không yêu cầu ứng dụng gọi equals theo một số lần cố định. HashMap có quyền tránh phép so bằng khi một bước lọc đã loại ứng viên.

### Tìm lại đúng đối tượng A đã lưu

Mã nội bộ phù hợp và tham chiếu khóa trùng ngay ở nút đầu. Không cần gọi A.equals(A) để biết đây là cùng đối tượng.

### Tìm một đối tượng A mới nhưng bằng khóa đã lưu

Hai tham chiếu khác nhau, mã băm trùng, nên phải dùng equals để xác định cùng khóa. Kết quả vẫn là alpha nếu hợp đồng khóa đúng.

### Tìm C bằng một đối tượng mới

Nút A có cùng mã nội bộ 1 nhưng equals trả false. Nút B có mã nội bộ 17, khác 1, nên không cần gọi equals trên B. Nút C có mã 1 và khóa bằng khóa dò, nên tìm được gamma.

### Không tìm thấy nhưng bucket vẫn có dữ liệu

Với khóa X có mã nội bộ 1 và khác A, C, thuật toán phải bác bỏ các ứng viên có mã phù hợp. Với khóa Z có mã 33, bucket 1 vẫn chứa dữ liệu nhưng không nút nào có mã 33, nên có thể kết luận không khớp mà không gọi equals cho các khóa đó.

Bởi vậy, dấu vết “không có equals được gọi” không chứng minh bucket chắc chắn rỗng. Nó cũng có thể có những nút bị loại ngay từ mã băm.

### Nếu bucket là cây

Một số bucket có thể được chuyển sang dạng cây thay vì luôn duyệt như chuỗi. Trong trường hợp đó, tìm kiếm đi theo cơ chế của nút cây. Không mô tả mọi HashMap như một mảng của danh sách mãi mãi, và không dùng dấu vết chuỗi của ví dụ nhỏ như cam kết cho bucket đã chuyển dạng.

## 8. Chương trình Java 17+ quan sát hashCode và equals

Tệp `HashMapLookupDemo.java` dùng một record Key bất biến. Trong ví dụ học cơ chế, cả `id` lẫn `rawHash` là dữ liệu tham gia equals; hashCode trả trường rawHash được cố ý chọn để tạo các trường hợp va chạm.

Cách thiết kế này giữ hợp đồng: nếu hai Key bằng nhau thì rawHash của chúng bằng nhau. Những id khác nhau vẫn có thể cùng rawHash. Nó là công cụ thí nghiệm, không phải gợi ý đưa một “mã băm do người dùng nhập” vào mọi khóa nghiệp vụ.

Danh sách `events` chỉ ghi lại các lời gọi trong một chương trình một luồng. Việc ghi dấu vết không tham gia quyết định equals; đây không phải một cách viết nhật ký dùng chung giữa nhiều luồng.

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class HashMapLookupDemo {
    private static final List<String> events = new ArrayList<>();

    record Key(String id, int rawHash) {
        Key {
            Objects.requireNonNull(id, "id");
        }

        @Override
        public int hashCode() {
            events.add("hash(" + id + ")=" + rawHash);
            return rawHash;
        }

        @Override
        public boolean equals(Object other) {
            if (!(other instanceof Key that)) {
                return false;
            }
            events.add("equals(" + id + "," + that.id + ")");
            return rawHash == that.rawHash && id.equals(that.id);
        }
    }

    static int spread(int rawHash) {
        return rawHash ^ (rawHash >>> 16);
    }

    static int bucket(int mixedHash, int capacity) {
        if (capacity <= 0 || (capacity & (capacity - 1)) != 0) {
            throw new IllegalArgumentException("capacity must be a power of two");
        }
        return mixedHash & (capacity - 1);
    }

    static void lookup(Map<Key, String> map, String label, Key key) {
        events.clear();
        String value = map.get(key);
        System.out.println(label + " get=" + value + " events=" + events);
    }

    public static void main(String[] args) {
        for (int raw : new int[] {1, 17, 65536, 2, -1}) {
            int mixed = spread(raw);
            System.out.println("raw=" + raw + " mixed=" + mixed
                    + " bucket16=" + bucket(mixed, 16)
                    + " bucket32=" + bucket(mixed, 32));
        }

        Key a = new Key("A", 1);
        Key b = new Key("B", 17);
        Key c = new Key("C", 1);
        Key d = new Key("D", 65536);
        Map<Key, String> map = new HashMap<>(16);
        map.put(a, "alpha");
        map.put(b, "beta");
        map.put(c, "gamma");
        map.put(d, "delta");

        System.out.println("initial size=" + map.size());
        lookup(map, "same reference A", a);
        lookup(map, "equal new A", new Key("A", 1));
        lookup(map, "equal new C", new Key("C", 1));
        lookup(map, "missing same hash X", new Key("X", 1));
        lookup(map, "missing other hash Z", new Key("Z", 33));
        lookup(map, "empty bucket E", new Key("E", 2));

        String previous = map.put(new Key("B", 17), "beta2");
        System.out.println("replace B previous=" + previous
                + " size=" + map.size());
        lookup(map, "B after replacement", new Key("B", 17));

        map.put(null, "nil");
        lookup(map, "null key", null);
        System.out.println("size with null key=" + map.size());

        map.put(new Key("C", 1), null);
        String cValue = map.get(new Key("C", 1));
        boolean cPresent = map.containsKey(new Key("C", 1));
        String missingValue = map.get(new Key("missing", 1));
        boolean missingPresent = map.containsKey(new Key("missing", 1));
        System.out.println("C value=" + cValue + " present=" + cPresent);
        System.out.println("missing value=" + missingValue
                + " present=" + missingPresent);

        Key aCopy = new Key("A", 1);
        Key cCopy = new Key("C", 1);
        events.clear();
        System.out.println("A equals new A=" + a.equals(aCopy));
        System.out.println("A equals C=" + a.equals(cCopy));
        System.out.println("A raw hash equals C raw hash="
                + (a.rawHash() == c.rawHash()));
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 -encoding UTF-8 HashMapLookupDemo.java
java HashMapLookupDemo
~~~

Dùng JDK 17 hoặc mới hơn hỗ trợ phiên bản đích 17. Chương trình tương thích API và cú pháp Java 17. Dấu vết dưới đây được đối chiếu với đường tìm chuỗi trong mã nguồn OpenJDK 17; chi tiết số lần gọi không phải một lời hứa chung cho mọi triển khai hoặc phiên bản HashMap.

Stdout chính xác:

~~~text
raw=1 mixed=1 bucket16=1 bucket32=1
raw=17 mixed=17 bucket16=1 bucket32=17
raw=65536 mixed=65537 bucket16=1 bucket32=1
raw=2 mixed=2 bucket16=2 bucket32=2
raw=-1 mixed=-65536 bucket16=0 bucket32=0
initial size=4
same reference A get=alpha events=[hash(A)=1]
equal new A get=alpha events=[hash(A)=1, equals(A,A)]
equal new C get=gamma events=[hash(C)=1, equals(C,A), equals(C,C)]
missing same hash X get=null events=[hash(X)=1, equals(X,A), equals(X,C)]
missing other hash Z get=null events=[hash(Z)=33]
empty bucket E get=null events=[hash(E)=2]
replace B previous=beta size=4
B after replacement get=beta2 events=[hash(B)=17, equals(B,B)]
null key get=nil events=[]
size with null key=5
C value=null present=true
missing value=null present=false
A equals new A=true
A equals C=false
A raw hash equals C raw hash=true
~~~

### Cách đọc bằng chứng

Năm dòng đầu là kết quả tính mô hình bucket cho hai dung lượng, không phải đọc dung lượng thật của Map bằng một API công khai.

`same reference A` chỉ ghi một lời gọi hashCode. `equal new A` còn có một phép equals. Cặp số hiệu A trong `equals(A,A)` là hai id cùng chữ A, không khẳng định hai đối tượng cùng tham chiếu.

`equal new C` xét equals với A rồi C; B bị loại bằng mã băm khác. `missing other hash Z` không có equals dù bucket mô hình cùng là 1. `empty bucket E` cũng không có equals nhưng vì một lý do khác: vị trí chọn không có ứng viên.

`replace B` trả giá trị cũ beta và kích thước vẫn bằng bốn, xác nhận thay giá trị theo khóa bằng nhau không thêm một khóa trùng. Khóa null được tìm mà không gọi phương thức trên một đối tượng Key nào. Hai dòng có giá trị null cuối cho thấy cần phân biệt “tìm được nút chứa null” với “không tìm được nút”.


## 9. Null trong kết quả tìm kiếm

Trên đường `get(key)`, có hai kết quả nội bộ khác nhau: không tìm thấy node phù hợp, hoặc tìm thấy node có giá trị `null`. API `get` đều có thể trả `null` cho cả hai. Khi cần biết khóa có mặt, dùng `containsKey` thay vì suy luận chỉ từ `get`.

~~~text
C → null, đã có trong Map       get(C) → null; containsKey(C) → true
X không có trong Map             get(X) → null; containsKey(X) → false
~~~

Khóa `null` cũng được `HashMap` hỗ trợ: triển khai OpenJDK chọn mã băm nội bộ 0 để định vị, nhưng vẫn phải kiểm tra đúng khóa trong bucket. Quy tắc chỉ một khóa `null`, nhiều giá trị `null` và hành vi của các phương thức cập nhật là trọng tâm của bài riêng về chính sách null.

## 10. Khóa biến đổi có thể làm hỏng đường tìm

Khi thêm ánh xạ, node lưu mã băm đã tính; khi tìm lại, `HashMap` tính mã từ khóa truy vấn. Nếu những trường tham gia `hashCode` hoặc `equals` bị sửa trong lúc đối tượng làm khóa, đường tìm có thể không nhận diện được ánh xạ cũ.

Ví dụ trong mô hình OpenJDK với bảng 16 bucket: node đã lưu mã 1, sau khi sửa khóa mã truy vấn thành 17. Cả hai vẫn chọn bucket 1, nhưng mã lưu và mã dò khác nhau nên ngay cả cùng tham chiếu khóa cũng có thể bị loại trước phép so bằng. Không dựa vào một kết quả lỗi cụ thể của khóa đã vi phạm điều kiện; hãy thiết kế dữ liệu định danh ổn định. Bài về khóa khả biến phân tích các lỗi và cách khắc phục kỹ hơn.

## 11. Resize làm thay đổi vị trí bucket

Chỉ số bucket phụ thuộc vào dung lượng của bảng hiện tại. Ví dụ mã nội bộ 17 chọn bucket `17 & 15 = 1` khi dung lượng 16 nhưng chọn `17 & 31 = 17` khi dung lượng 32. Khi bảng tăng kích thước, triển khai phải bố trí lại các ánh xạ; chương trình ứng dụng không được lưu chỉ số bucket tự tính như một định danh cố định.

Tăng dung lượng có thể tách các khóa có mã khác nhau đang cùng bucket, nhưng không tự tách những khóa có mã băm nội bộ giống hệt. Cơ chế ngưỡng mở rộng, chia bucket và chi phí resize được triển khai chi tiết ở bài capacity/load factor.

## 12. Chi phí của một lần tìm

Với phân bố mã băm thích hợp và chi phí `hashCode`/`equals` hợp lý, tra cứu có hiệu năng kỳ vọng hằng số. Điều đó không hứa mọi lời gọi `get` thực hiện đúng một phép so hay mất thời gian bằng nhau.

~~~text
chi phí tìm = tính hashCode + chọn bucket + xét ứng viên + so equals khi cần
~~~

Bucket chuỗi có L node có thể cần xét đến L ứng viên; mã băm khác nhau có thể bị loại trước `equals`. Trong bucket cây, đường tìm còn phụ thuộc điều kiện của triển khai và khả năng phân biệt khóa. Ví dụ đếm lời gọi ở trên chỉ chứng minh một dấu vết cụ thể, không phải phép đo thời gian. Các bài hiệu năng và cây hóa bucket sẽ phân tích sâu những giới hạn này.

## 13. Chẩn đoán sai lệch trong đường tìm

| Quan sát hoặc suy luận sai | Kiểm tra chính xác hơn |
| --- | --- |
| `hashCode` chính là bucket | Bước trộn mã và dung lượng bảng còn quyết định chỉ số |
| Hai khóa cùng bucket phải cùng ánh xạ | So tiếp mã nội bộ và khóa theo `equals` |
| Cùng `hashCode` thì `equals` phải true | Khóa khác nhau được phép va chạm |
| Không thấy gọi `equals` nghĩa là bucket rỗng | Ứng viên có thể bị loại vì mã băm khác |
| Dùng chính tham chiếu khóa đã sửa sẽ luôn `get` được | Mã băm lưu trong node có thể khác mã mới |
| `get` bằng `null` là chắc chắn không có khóa | `containsKey` phân biệt ánh xạ chứa null với vắng mặt |

Khi một khóa đáng lẽ có nhưng không được tìm thấy, hãy kiểm tra định nghĩa danh tính, tính nhất quán `equals`/`hashCode`, việc thay đổi khóa sau khi chèn và sự khác nhau giữa `null` với vắng mặt. Không cần phản chiếu đọc trường private để chẩn đoán các lỗi này.

## 14. Bài tập và lời giải

### Bài 1 — Phân biệt size và capacity

Một HashMap có bốn ánh xạ, bảng mô hình có dung lượng 16. Có thể kết luận có 12 bucket rỗng không?

**Lời giải:** không. Bốn ánh xạ có thể rơi vào cùng bucket hoặc nhiều bucket khác nhau. Nếu ở bốn bucket khác nhau mới có 12 vị trí rỗng; nếu cả bốn ở một bucket thì có 15 vị trí rỗng. Size đếm ánh xạ, không đếm bucket đã dùng.

### Bài 2 — Tính chỉ số

Mã nội bộ là 17. Với dung lượng 16 và 32, chỉ số trong mô hình OpenJDK được tính ra bao nhiêu?

**Lời giải:** `17 & 15 = 1` và `17 & 31 = 17`. Cùng mã không có nghĩa chỉ số cố định khi dung lượng đổi.

### Bài 3 — Cùng bucket, khác mã

A có mixedHash 1, B có mixedHash 17. Ở bảng 16 bucket, chúng cùng bucket nào? Khi tìm một khóa có mã 1, có bắt buộc gọi equals với B không?

**Lời giải:** cùng bucket 1. Không bắt buộc gọi equals với B trong đường tìm đã mô tả, vì mã 17 lưu trong nút B khác mã 1 đang tìm và có thể loại B sớm.

### Bài 4 — Cùng mã, khác khóa

A và C cùng hashCode 1 nhưng equals false. Thêm A rồi C có làm giá trị của A bị thay không?

**Lời giải:** không chỉ vì mã băm giống nhau. Chúng là hai khóa khác nhau theo hợp đồng đã chọn nên có thể cùng tồn tại. Chỉ khi khóa được nhận diện là bằng nhau thì put mới thay giá trị cho cùng ánh xạ.

### Bài 5 — Đọc dấu vết tìm C

Vì sao chương trình in `equals(C,A)` rồi `equals(C,C)` mà không có `equals(C,B)`?

**Lời giải:** A và C có mã nội bộ 1 nên cần so khóa; B có mã 17 nên bị loại trước khi gọi equals. Hai chữ C trong dấu vết thứ hai là id giống nhau của hai đối tượng khác tham chiếu.

### Bài 6 — Không có equals có chứng minh không có ứng viên?

Tìm Z có mã 33, cùng bucket mô hình với A/B/C/D ở dung lượng 16, nhưng nhật ký chỉ có hashCode. Có phải bảng hỏng không?

**Lời giải:** không. Bucket có nút nhưng không nút nào giữ mã nội bộ 33, nên các nút có thể bị loại mà không cần equals. Đường tìm hoạt động đúng theo bộ lọc mã băm.

### Bài 7 — Khóa mới bằng khóa cũ

Đã lưu Key("A", 1). Dùng một đối tượng mới Key("A", 1) để get có cần cùng địa chỉ tham chiếu không?

**Lời giải:** không. Hai Key bằng nhau theo equals và có mã nhất quán; HashMap có thể tìm qua bước so bằng khi hai tham chiếu khác nhau. Dùng == để quyết định khóa có tra được hay không sẽ bỏ qua cơ chế này.

### Bài 8 — Hai kết quả null

C đang ánh xạ tới null, X vắng mặt. Cả get(C) và get(X) đều trả null. Kết quả nào giúp phân biệt và điều này liên hệ gì với nút nội bộ?

**Lời giải:** containsKey(C) là true, containsKey(X) là false khi nguồn không đổi. C tìm được một nút có value null; X không có nút khớp.

### Bài 9 — Hash âm và Math.abs

Có cần chuyển mã băm âm thành dương trước khi dùng HashMap không? Vì sao không tự mô phỏng bằng Math.abs rồi chia dư?

**Lời giải:** không. HashMap xử lý int theo cơ chế nội bộ; mặt nạ với n - 1 tạo chỉ số hợp lệ trong mô hình này. Math.abs rồi chia dư là công thức khác, và Math.abs của Integer.MIN_VALUE vẫn âm.

### Bài 10 — Khóa bị thay đổi nhưng bucket chưa đổi

Khóa lúc thêm có mã nội bộ 1; sau đó dữ liệu khóa bị sửa làm mã thành 17. Cả hai mã vẫn vào bucket 1 ở dung lượng 16. Có chắc get sẽ tìm thấy vì cùng bucket không?

**Lời giải:** không. Nút còn giữ mã 1 có thể bị loại bởi mã 17 của lần dò trước khi xét cùng tham chiếu hoặc equals. Đây là một lý do tránh khóa thay đổi, không phải một tình trạng hợp lệ để ứng dụng dựa vào kết quả cụ thể.

### Bài 11 — Tăng bảng và mã băm giống hệt

Có rất nhiều khóa khác nhau nhưng tất cả hashCode đều bằng 7. Chỉ tăng dung lượng bảng có tự chia chúng ra nhiều bucket không?

**Lời giải:** không theo công thức đã xét: cùng mã ban đầu cho cùng mã sau trộn và cùng chỉ số ở mỗi dung lượng. Cần xem lại cách băm và mô hình khóa, không chỉ tăng số vị trí.

### Bài 12 — Mở rộng thí nghiệm

Hãy thêm hai khóa có rawHash khác nhau nhưng cùng bucket ở dung lượng 16, rồi tìm bằng một đối tượng mới bằng một trong hai khóa. Cần giữ điều gì để thí nghiệm có ý nghĩa?

**Lời giải:** có thể chọn rawHash 3 và 19, cả hai có mã sau trộn tương ứng 3 và 19 và cùng bucket 3 ở dung lượng 16. Dùng hai id riêng, giữ rawHash trong dữ liệu so bằng như Key của chương trình, không thay đổi khóa sau khi thêm. Quan sát dấu vết để thấy ứng viên khác mã có thể bị bỏ qua. Không suy ra số lần gọi hoặc thứ tự nút là một bảo đảm API cho mọi phiên bản.

## 15. Tự kiểm tra mô hình tìm khóa

Hãy tự giải thích một lần get theo ba tầng: chọn phạm vi bằng mã băm, lọc và so khóa trong bucket, rồi đọc giá trị của nút đã khớp. Nếu trộn lẫn ba tầng này, rất dễ đồng nhất bucket với khóa hoặc giá trị null với việc không tìm thấy.

Khi thiết kế khóa, ưu tiên tính đúng của equals/hashCode và sự ổn định của dữ liệu nhận diện. Khi đánh giá hiệu năng, xét cả phân bố bucket và chi phí các phương thức của khóa. Khi đọc mã nguồn, ghi rõ phiên bản và tách chi tiết triển khai khỏi hợp đồng công khai.

Bucket giúp thu hẹp nơi tìm; mã băm giúp lọc ứng viên; phép nhận diện khóa quyết định ánh xạ nào thực sự khớp. Cả ba vai trò kết hợp mới tạo nên quy trình tìm khóa của HashMap.

