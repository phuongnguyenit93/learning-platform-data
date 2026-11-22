# Phối hợp hashCode và equals khi put, get, remove

## 1. Hai nhiệm vụ: tìm vùng ứng viên và nhận diện đúng khóa

Một HashMap cần trả lời câu hỏi: “Khóa đang hỏi có phải cùng khóa logic với một ánh xạ đã lưu không?”. Nếu phải so sánh với mọi khóa mỗi lần đọc, việc tra cứu sẽ tốn nhiều công sức khi dữ liệu lớn.

HashMap phối hợp hai công cụ:

- `hashCode()` giúp định hướng đến một vùng chứa ứng viên.
- `equals()` xác định sự bằng nhau về mặt logic khi cần phân biệt các khóa ứng viên.

Ví dụ một đối tượng khóa mang mã khách hàng C01. Hai đối tượng được tạo riêng nhưng cùng biểu thị C01 phải có thể tìm cùng một ánh xạ, nếu mô hình định danh của ứng dụng quy định như vậy.

Ngược lại, hai khách hàng C01 và C02 có thể tình cờ cho cùng mã băm. HashMap vẫn phải giữ chúng như hai khóa khác nhau nếu equals trả false.

Bài này giải thích đường đi của put, get và remove, phân biệt các loại va chạm, và cho thấy vì sao khóa sai hợp đồng hoặc khóa bị sửa sau khi chèn dễ làm tra cứu không còn như mong đợi.

## 2. Hợp đồng phải đúng trước khi xét thuật toán

### 2.1. Bằng nhau kéo theo cùng mã băm

Hai quy tắc quan trọng:

```text
a.equals(b) == true  →  a.hashCode() == b.hashCode()
cùng hashCode       ↛  bắt buộc equals bằng true
```

Khi thông tin liên quan đến phép bằng không đổi, các lần gọi hashCode trên cùng đối tượng trong một lần chạy cũng phải nhất quán. Một hashCode tự đổi theo số lần gọi hoặc theo ngẫu nhiên sẽ làm đường tìm không ổn định.

Chiều thứ hai không phải bảo đảm. Mã băm là số nguyên có miền giá trị hữu hạn, không phải một định danh duy nhất không thể trùng.

Một hàm hashCode luôn trả 7 có thể vẫn đúng điều kiện “hai khóa bằng nhau có cùng mã băm”. Nhưng phân bố đó kém và có thể làm tìm kiếm chậm. Đúng hợp đồng và có hiệu năng tốt là hai yêu cầu cần phân biệt.

Hợp đồng gốc được mô tả trong [Object.equals và Object.hashCode Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html).

### 2.2. equals phải là một quan hệ nhất quán

Khi xây khóa theo giá trị, equals cần đáp ứng các tính chất như phản xạ, đối xứng, bắc cầu, nhất quán khi thông tin nhận diện không đổi, và trả false khi so với null.

Đừng viết một lớp mà a bằng b nhưng b không bằng a rồi mong HashMap sửa sự mâu thuẫn ấy. Hướng gọi equals có thể làm kết quả trở nên khó hiểu nếu bản thân quan hệ đã sai.

Nếu ghi đè equals, phải đồng thời bảo đảm hashCode phù hợp. Chỉ ghi đè hashCode mà vẫn dùng phép bằng theo tham chiếu của Object không tự tạo ra khóa theo nội dung.

### 2.3. Cùng tham chiếu khác với cùng khóa logic

`a == b` kiểm tra hai tham chiếu cùng đối tượng. `a.equals(b)` có thể quy định hai đối tượng khác nhau vẫn là cùng định danh logic.

Một lớp thường chưa ghi đè equals sẽ kế thừa hành vi bằng theo tham chiếu từ Object. Khi đó hai đối tượng có các trường giống nhau chưa chắc là cùng khóa.

Record có thể giúp khi các thành phần của record đúng là những dữ liệu nhận diện cần dùng. Phép bằng và mã băm mặc định của record dựa trên các thành phần; vẫn cần quan tâm dữ liệu bên trong có thay đổi được hay không.

## 3. Từ hashCode đến bucket trong OpenJDK

### 3.1. Bucket là vùng chứa ứng viên

HashMap tổ chức một bảng các vùng chứa, thường gọi là **bucket**. Một bucket có thể chứa không có, một hoặc nhiều ánh xạ.

Mô hình:

```text
khóa cần thao tác
    ↓ hashCode
mã băm của khóa
    ↓ trộn một số bit
hash dùng trong cấu trúc
    ↓ chọn chỉ số
bucket ứng viên
    ↓ kiểm tra hash và khóa
ánh xạ đúng hoặc không tìm thấy
```

HashMap không dùng một mã băm làm chỗ duy nhất chỉ chứa được một entry. Va chạm là trường hợp cấu trúc phải xử lý bình thường.

### 3.2. Công thức là chi tiết cài đặt, không phải API bắt người gọi tự tính

Trong OpenJDK 17u, với khóa khác null, một phép trộn được dùng có dạng:

```java
int h = key.hashCode();
int hash = h ^ (h >>> 16);
```

Khi bảng đã được cấp phát và có chiều dài n là lũy thừa của 2:

```java
int index = (n - 1) & hash;
```

Đây là các biểu thức minh họa từ cơ chế cài đặt, không phải một chương trình độc lập. Người gọi HashMap không cần tự tính index trước put/get/remove.

Có thể đối chiếu [mã nguồn HashMap OpenJDK 17u](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/HashMap.java). Hợp đồng công khai về khóa và thao tác map không buộc mọi phiên bản cài đặt phải giữ nguyên một công thức nội bộ.

Mã băm có thể là số âm. Người viết khóa không phải biến hashCode thành một số không âm để HashMap dùng được. Cũng không dùng Math.abs như một yêu cầu bắt buộc của hợp đồng hashCode.

### 3.3. Cùng bucket chưa chắc cùng hash

Giả sử n bằng 16 và các hash đã trộn là 1 và 17:

```text
15 & 1  = 1
15 & 17 = 1
```

Cả hai hướng vào bucket 1 nhưng hai hash vẫn khác nhau. Bảng chỉ dùng một phần thông tin để chọn vùng chứa; node còn giữ hash để hỗ trợ lọc ứng viên.

Vì vậy phải phân biệt:

| Quan hệ | Điều suy ra được |
| --- | --- |
| Hai khóa bằng nhau và đúng hợp đồng | Chúng có cùng hashCode và được định hướng phù hợp để tìm nhau |
| Cùng hashCode | Có thể là hai khóa khác nhau |
| Cùng hash đã trộn | Vẫn có thể cần kiểm tra khóa |
| Cùng chỉ số bucket | Càng không đủ để kết luận cùng khóa |

“Va chạm bucket” rộng hơn trường hợp “hai khóa trả cùng hashCode”.

## 4. Cách một ứng viên được xác nhận

Trong đường xử lý thông thường của OpenJDK, điều kiện kiểm tra có dạng khái niệm:

```text
hash lưu trong node bằng hash đang tìm
VÀ
(
    khóa lưu cùng tham chiếu với khóa đang tìm
    HOẶC
    khóa đang tìm khác null và bằng khóa lưu theo equals
)
```

Những điểm cần giữ:

1. Hash lọc vùng và ứng viên; nó không thay thế định nghĩa bằng nhau.
2. Cùng tham chiếu có thể là một đường xác nhận nhanh.
3. Nếu cần gọi equals, việc so khóa diễn ra sau khi đã có các điều kiện định hướng phù hợp.
4. Một lookup không có nghĩa bắt buộc gọi equals với mọi khóa đã lưu.

Trong các đoạn tìm thông thường của OpenJDK, equals được gọi từ khóa của thao tác tới khóa đang lưu, dạng `lookupKey.equals(storedKey)`. Khi equals đúng tính đối xứng, hướng đó không làm thay đổi kết luận logic.

Không xây kiểm thử nghiệp vụ yêu cầu chính xác bao nhiêu lần equals/hashCode phải được gọi hoặc gọi theo một thứ tự nội bộ cố định. Cấu trúc có thể tối ưu, thay đổi đường tìm hoặc xử lý bucket dạng cây khi phù hợp.

Bucket có nhiều phần tử không phải lúc nào cũng chỉ là một danh sách liên kết. Chi tiết danh sách/cây giúp cài đặt xử lý va chạm, nhưng không thay đổi nghĩa “cùng khóa logic theo hợp đồng”.

## 5. put: cập nhật khóa cũ hoặc thêm một khóa khác

### 5.1. Khóa đã có theo phép bằng

Giả sử đã lưu:

```text
Key("A") → first-A
```

Gọi put với một đối tượng Key("A") khác, nhưng bằng nhau và có hash đúng hợp đồng:

```text
put(new Key("A"), updated-A)
```

HashMap tìm được ánh xạ ứng viên, xác nhận cùng khóa và thay giá trị. Size không tăng. Giá trị trả về là first-A, tức giá trị trước thao tác.

Không có yêu cầu phải giữ lại đúng tham chiếu ban đầu trong mã gọi rồi mới cập nhật được. Đó là lợi ích của mô hình khóa theo giá trị.

### 5.2. Cùng hash nhưng equals false

Giả sử Key("A") và Key("B") đều có hashCode bằng 7, nhưng không bằng nhau. Put B phải giữ một ánh xạ riêng:

```text
Key("A") → first-A
Key("B") → first-B
```

B không ghi đè A chỉ vì cùng hash hoặc cùng bucket. HashMap xử lý va chạm rồi thêm entry cho khóa khác.

### 5.3. Giá trị không quyết định tính trùng của khóa

HashMap chọn ánh xạ theo khóa. Hai value bằng nhau không làm hai khóa bị nhập lại; hai value khác nhau cũng không làm một khóa đã bằng nhau trở thành hai khóa.

Nếu put “làm mất” một dữ liệu, hãy kiểm tra quy tắc equals/hashCode của khóa và miền định danh, thay vì chỉ nhìn giá trị đang ghi.

Hành vi put và tính duy nhất của khóa có thể đối chiếu ở [HashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).

## 6. get: cùng đường nhận diện nhưng chỉ đọc giá trị

Get thực hiện việc tìm ứng viên theo hash và nhận diện khóa. Nếu tìm thấy, nó trả value của entry. Nếu không tìm thấy, nó trả null.

Một đối tượng khóa được tạo mới vẫn có thể get được dữ liệu nếu bằng khóa đã lưu và có mã băm phù hợp. Ngược lại, một đối tượng có cùng hash nhưng không bằng khóa không phải một kết quả khớp.

Với một map có khóa A và B cùng hash:

```text
get(Key("A")) → giá trị của A
get(Key("B")) → giá trị của B
get(Key("C")) → không tìm thấy, nếu C khác cả A và B
```

Get không tra cứu bằng hashCode của value. Nếu cần tìm các khóa theo value, đó là một bài toán khác với đường tìm khóa của HashMap.

### Null không tự chứng minh khóa vắng mặt

HashMap cho phép giá trị null. Vì vậy get trả null có thể là:

- Không có entry phù hợp.
- Có entry phù hợp nhưng value đang là null.

ContainsKey giúp phân biệt sự tồn tại trong ngữ cảnh cần biết điều đó. Bản thân thông tin tìm đúng khóa và thông tin value khác null là hai vấn đề riêng.

## 7. remove: tìm đúng khóa rồi tháo ánh xạ đó

Remove một đối số dùng khóa để tìm entry như trên, sau đó loại ánh xạ phù hợp và trả giá trị cũ.

Nếu A và B cùng hash nhưng không bằng nhau, remove(A) không được xóa B chỉ vì B cùng bucket. Nếu không có khóa cần tìm, remove trả null và không xóa các khóa khác.

Với value null, remove cũng có thể trả null sau khi đã xóa thành công. Không dùng riêng kết quả null để khẳng định thao tác không tìm thấy khóa.

Biến thể `remove(key, expectedValue)` còn bổ sung điều kiện về value sau khi xác định ánh xạ theo key. Điều đó không biến quá trình tìm khóa thành tìm theo hashCode của value.

Nếu thao tác remove thất bại do khóa tự thay đổi hoặc vi phạm hợp đồng, gọi lặp lại với những đối tượng trông giống nhau không sửa được thiết kế khóa. Cần xem dữ liệu nhận diện và mã băm đang được tính từ đâu.

## 8. Chương trình chạy: va chạm hợp lệ và khóa bằng nhau

Lưu thành **HashLookupDemo.java**:

```java
import java.util.HashMap;
import java.util.Map;

public class HashLookupDemo {
    record CollisionKey(String code) {
        @Override
        public int hashCode() {
            return 7;
        }
    }

    public static void main(String[] args) {
        CollisionKey a = new CollisionKey("A");
        CollisionKey equalA = new CollisionKey("A");
        CollisionKey b = new CollisionKey("B");
        Map<CollisionKey, String> map = new HashMap<>();

        System.out.println("same reference A: " + (a == equalA));
        System.out.println("equal logical A: " + a.equals(equalA));
        System.out.println("A and B same hash: " + (a.hashCode() == b.hashCode()));
        System.out.println("A equals B: " + a.equals(b));
        System.out.println("first put A old: " + map.put(a, "first-A"));
        System.out.println("first put B old: " + map.put(b, "first-B"));
        System.out.println("size with collision: " + map.size());
        System.out.println("get equal A: " + map.get(equalA));
        System.out.println("equal A put old: " + map.put(equalA, "updated-A"));
        System.out.println("size after equal-key put: " + map.size());
        System.out.println("get original A: " + map.get(a));
        System.out.println("get B: " + map.get(new CollisionKey("B")));

        System.out.println("remove equal A: " + map.remove(new CollisionKey("A")));
        System.out.println("A still present: " + map.containsKey(a));
        System.out.println("B still present: " + map.containsKey(b));
        System.out.println("remove missing C: " + map.remove(new CollisionKey("C")));
        System.out.println("size after removals: " + map.size());

        map.put(null, "first-null");
        System.out.println("get null key: " + map.get(null));
        System.out.println("second null-key put old: " + map.put(null, "second-null"));
        System.out.println("size with null key: " + map.size());
        System.out.println("remove null key: " + map.remove(null));

        CollisionKey n = new CollisionKey("N");
        map.put(n, null);
        System.out.println("get mapped null: " + map.get(new CollisionKey("N")));
        System.out.println("contains mapped-null key: " + map.containsKey(n));
        System.out.println("remove mapped null old: " + map.remove(new CollisionKey("N")));
        System.out.println("mapped-null key remains: " + map.containsKey(n));
        System.out.println("final size: " + map.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 HashLookupDemo.java
java HashLookupDemo
```

Stdout chính xác:

```text
same reference A: false
equal logical A: true
A and B same hash: true
A equals B: false
first put A old: null
first put B old: null
size with collision: 2
get equal A: first-A
equal A put old: first-A
size after equal-key put: 2
get original A: updated-A
get B: first-B
remove equal A: updated-A
A still present: false
B still present: true
remove missing C: null
size after removals: 1
get null key: first-null
second null-key put old: first-null
size with null key: 2
remove null key: second-null
get mapped null: null
contains mapped-null key: true
remove mapped null old: null
mapped-null key remains: false
final size: 1
```

CollisionKey là record có thành phần code. Equals mặc định của record phân biệt A với B và nhận hai bản A là bằng nhau. HashCode cố ý luôn trả 7 để tạo va chạm có thể quan sát.

Hàm băm hằng ở đây dùng cho thí nghiệm; không phải khuyến nghị phân bố hash cho khóa trong ứng dụng.

Các kết quả giải thích được bằng cùng một mô hình:

- a và equalA khác tham chiếu nhưng bằng khóa logic.
- A và B có cùng hash nhưng là hai khóa nên size bằng 2.
- Put equalA thay value của A và giữ size.
- Get/remove bằng một bản A mới vẫn tìm đúng ánh xạ.
- Xóa A không ảnh hưởng B.
- Khóa null được lưu/cập nhật/xóa như một khóa riêng được HashMap hỗ trợ.
- Value null vẫn là một ánh xạ thực, và remove value null có thể trả null dù đã xóa khóa.

Các chương trình trong bài được biên dịch với `--release 17` và chạy trên OpenJDK 24.0.2. Cờ đó kiểm tra ngôn ngữ/API mục tiêu Java 17 và sinh bytecode tương ứng; JVM chạy ví dụ vẫn là bản đã nêu.

## 9. Null key đi qua nhánh riêng

HashMap chấp nhận một khóa null. Vì không thể gọi null.hashCode(), cài đặt OpenJDK dùng hash 0 cho nhánh khóa null.

Điều này không có nghĩa bucket 0 chỉ được chứa null. Một khóa khác null có hash phù hợp vẫn có thể cùng bucket, nhưng phép nhận diện khóa phải phân biệt nó với null.

Theo hợp đồng equals hợp lệ, một đối tượng khác null không được coi null là bằng chính nó. Vì vậy một khóa thường có hash 0 không tự trở thành khóa null.

Nhiều lần put(null, value) cập nhật cùng ánh xạ null, không tạo ra nhiều khóa null. Các lớp map khác có thể cấm null; đây là chính sách của HashMap, không phải điều mọi Map đều cho phép.

## 10. Hai lỗi thiết kế khóa và dấu hiệu quan sát

### 10.1. Equals đúng ý nhưng hashCode không nhất quán

Giả sử hai đối tượng cùng mã "same" có equals true nhưng hashCode lần lượt là 1 và 2.

Định nghĩa khóa đã vi phạm hợp đồng. HashMap có thể định hướng thao tác tới các vùng khác nhau và không gọi equals giữa hai đối tượng như người viết mong đợi. Get bằng bản “bằng nhau” có thể không tìm thấy; put có thể để xuất hiện các entry nhìn như trùng định danh logic.

Không sửa bằng cách ép HashMap quét hết mọi khóa. Cần sửa hashCode để mọi khóa bằng nhau cùng mã băm theo hợp đồng.

### 10.2. Khóa bị sửa sau khi đã lưu

Giả sử một khóa có id bằng 1 khi đưa vào map và hashCode dựa trên id. Sau đó id bị đổi thành 17.

Node đã được đặt vào cấu trúc theo hash ở lúc thêm. Thao tác get/remove mới tính hash từ trạng thái mới của khóa. Hai trạng thái không còn nhất quán với nhau.

Ngay cả cùng tham chiếu cũng không phải một bảo đảm cứu được tra cứu: đường lọc hash có thể không đến được bước xác nhận tham chiếu.

Trong mô hình bảng 16 ô của OpenJDK, hash 1 và 17 thậm chí có thể cùng bucket, nhưng hash đầy đủ lưu ở node và hash đang tìm vẫn khác. Như vậy “vẫn cùng bucket” cũng không đủ để khóa bị sửa hoạt động đúng.

Map cảnh báo hành vi không được xác định khi khóa bị thay đổi theo cách ảnh hưởng phép bằng trong lúc làm khóa. Xem [ghi chú khóa thay đổi được của Map Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html).

## 11. Chương trình quan sát lỗi: không phải hợp đồng để dựa vào

Lưu thành **BrokenHashKeyObservation.java**:

```java
import java.util.HashMap;
import java.util.Map;

public class BrokenHashKeyObservation {
    static final class BadHashKey {
        private final String code;
        private final int forcedHash;

        BadHashKey(String code, int forcedHash) {
            this.code = code;
            this.forcedHash = forcedHash;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof BadHashKey key && code.equals(key.code);
        }

        @Override
        public int hashCode() {
            return forcedHash;
        }
    }

    static final class MutableKey {
        int id;

        MutableKey(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof MutableKey key && id == key.id;
        }

        @Override
        public int hashCode() {
            return id;
        }
    }

    public static void main(String[] args) {
        BadHashKey first = new BadHashKey("same", 1);
        BadHashKey equalButDifferentHash = new BadHashKey("same", 2);
        Map<BadHashKey, String> invalid = new HashMap<>();
        invalid.put(first, "stored");

        System.out.println("bad keys equals: " + first.equals(equalButDifferentHash));
        System.out.println("bad keys same hash: "
                + (first.hashCode() == equalButDifferentHash.hashCode()));
        System.out.println("observed bad lookup: " + invalid.get(equalButDifferentHash));
        invalid.put(equalButDifferentHash, "second");
        System.out.println("observed bad map size: " + invalid.size());

        MutableKey key = new MutableKey(1);
        Map<MutableKey, String> mutable = new HashMap<>(16);
        mutable.put(key, "payload");
        System.out.println("before key change: " + mutable.get(key));
        key.id = 17;
        System.out.println("observed changed-key get: " + mutable.get(key));
        System.out.println("observed changed-key remove: " + mutable.remove(key));
        System.out.println("observed changed-key size: " + mutable.size());
        System.out.println("observed entry still holds reference: "
                + (mutable.keySet().iterator().next() == key));
    }
}
```

Lệnh chạy:

```shell
javac --release 17 -encoding UTF-8 BrokenHashKeyObservation.java
java BrokenHashKeyObservation
```

Stdout quan sát trên môi trường kiểm tra:

```text
bad keys equals: true
bad keys same hash: false
observed bad lookup: null
observed bad map size: 2
before key change: payload
observed changed-key get: null
observed changed-key remove: null
observed changed-key size: 1
observed entry still holds reference: true
```

BadHashKey cố ý sai hợp đồng: equals chỉ xét code nhưng hashCode còn tùy một số được truyền riêng. Hai khóa "same" có equals true mà hash khác.

MutableKey cố ý sửa id sau khi chèn. Trong lần quan sát, get và remove không tìm được, nhưng size vẫn là 1 và entry còn giữ chính tham chiếu khóa ấy. Điều này giúp thấy dữ liệu không nhất thiết bị xóa khỏi cấu trúc chỉ vì tra cứu không ra.

**Những dòng observed minh họa hậu quả trên môi trường đã nêu, không phải hành vi được bảo đảm cho khóa sai hợp đồng hoặc khóa bị sửa trên mọi Java 17+.** Không viết kiểm thử sản phẩm bắt HashMap phải tái hiện chính xác các kết quả lỗi ấy.

Không dùng hai lớp này làm mẫu thiết kế đúng. Chúng là thí nghiệm để hiểu vì sao yêu cầu đối với khóa phải được tôn trọng.

## 12. Thiết kế khóa dùng được cho cả ba thao tác

### 12.1. Chọn đúng các thành phần định danh

Ví dụ một khóa ghép:

```java
// Khai báo minh họa đặt trong một lớp:
record CustomerKey(String organization, long customerId) {}
```

Hai CustomerKey cùng organization và customerId là cùng khóa logic. Khác organization có thể là hai khách hàng khác nhau dù cùng số customerId.

Những thành phần này cần phản ánh đúng miền dữ liệu, không chọn tùy ý để tạo nhiều hash khác nhau. Một hàm hash tốt không sửa được một mô hình equals đang nhập hai thực thể khác nhau làm một.

### 12.2. Giữ thông tin nhận diện ổn định

Ưu tiên String, số, enum hoặc các kiểu giá trị phù hợp và ổn định làm thành phần khóa.

Một trường final chỉ ngăn đổi tham chiếu của trường, không tự làm đối tượng bên trong bất biến. Nếu khóa chứa một List thay đổi được và equals/hashCode phụ thuộc nội dung List, sửa List vẫn có thể đổi ý nghĩa khóa.

Khi định danh phải thay đổi, thiết kế việc bỏ ánh xạ với khóa cũ rồi thêm ánh xạ bằng khóa mới theo chính sách ứng dụng. Không sửa khóa đang nằm trong map rồi trông chờ việc tăng dung lượng sẽ tự sửa lại mọi thứ.

### 12.3. Không đưa trường thay đổi thường xuyên vào khóa nếu nó không phải định danh

Tên hiển thị, bộ đếm, trạng thái phiên làm việc hoặc ngày cập nhật có thể thay đổi trong quá trình sử dụng. Nếu chúng không thuộc định danh cần phân biệt, không nên đưa chúng vào equals/hashCode của khóa chỉ vì chúng có sẵn trong lớp.

Có thể giữ mã định danh làm khóa và đặt dữ liệu thay đổi trong value. Khi value đổi, đường nhận diện khóa vẫn ổn định.

Nhưng nếu nghiệp vụ thật sự cần một ảnh chụp đầy đủ làm khóa, phải tạo một giá trị ảnh chụp ổn định và hiểu ý nghĩa đó. Không có quy tắc rằng mọi lớp có nhiều trường đều phải so tất cả hoặc chỉ một trường; mô hình định danh quyết định.

## 13. Hiệu năng và kiểm thử: đừng kiểm tra nhầm một chi tiết tối ưu

HashMap có hiệu năng tra cứu tốt khi mã băm phân bố phù hợp. Nhiều khóa cùng hash làm tăng công việc phân biệt ứng viên. Những cơ chế xử lý va chạm có thể giúp một số trường hợp, nhưng không biến một hàm băm hằng thành lựa chọn tốt cho mọi dữ liệu.

Một lần equals/hashCode phức tạp cũng có chi phí riêng. Không coi “tra cứu O(1) trung bình” là bằng không công việc hoặc luôn nhanh bất kể cách định nghĩa khóa.

Các kiểm thử có ý nghĩa cho một kiểu khóa gồm:

- Hai đối tượng có cùng định danh: equals true và hashCode bằng nhau.
- Hai định danh khác nhau: không bị equals nhận nhầm; hash vẫn được phép trùng.
- Put bằng bản khóa tương đương cập nhật một ánh xạ, size không tăng.
- Get và remove bằng bản khóa tương đương đều tìm đúng.
- Các khóa va chạm vẫn giữ/tìm/xóa độc lập.
- Những thành phần định danh không bị thay đổi trong vòng đời làm khóa.

Không cần buộc mọi cặp khóa khác nhau phải có hashCode khác nhau. Cũng không buộc hashCode phải giống giữa mọi lần chạy chương trình nếu kiểu đó không có hợp đồng như vậy.

Đừng dựa vào thứ tự duyệt HashMap hoặc số lần gọi equals chính xác để xác nhận đúng mô hình khóa. Hãy kiểm tra kết quả nghiệp vụ và hợp đồng bằng nhau.

HashMap cũng không tự an toàn cho cập nhật đồng thời. Một equals/hashCode đúng không thay thế yêu cầu chọn cấu trúc hoặc đồng bộ phù hợp khi nhiều luồng cùng sửa dữ liệu.

## 14. Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân cần xem | Cách sửa suy luận |
| --- | --- | --- |
| Hai khóa cùng mã băm bị tưởng ghi đè nhau | Nhầm hash bằng định danh | Kiểm tra equals, không chỉ hashCode |
| Tạo đối tượng khóa mới rồi get không ra | Chưa có equals theo giá trị hoặc hash không phù hợp | Kiểm tra cả hai phương thức |
| Equals true nhưng map có hai entry nhìn trùng | HashCode có thể sai hợp đồng | Bảo đảm bằng nhau kéo theo cùng mã băm |
| Put cập nhật giá trị mà size không tăng | Khóa tương đương đã tồn tại | Đây có thể đúng hành vi Map |
| Cùng tham chiếu nhưng get/remove thất bại | Khóa đã đổi thông tin nhận diện | Giữ khóa ổn định |
| Dữ liệu vẫn còn khi duyệt nhưng get không ra | Có thể là khóa thay đổi được | Không xem việc còn entry là bằng chứng đường tìm vẫn đúng |
| Remove trả null nên tưởng không xóa | Value cũ có thể là null | Phân biệt tồn tại khóa với giá trị |
| Cùng bucket nên tưởng chắc gọi equals | Node còn có điều kiện hash | Tách index bucket khỏi hash đầy đủ |
| Hàm băm hằng “đúng nên chắc nhanh” | Đúng hợp đồng nhưng phân bố kém | Thiết kế hash phù hợp dữ liệu |
| Key có List final nhưng vẫn đổi hash | Nội dung đối tượng bên trong thay đổi | Xét tính ổn định sâu của dữ liệu nhận diện |

## 15. Bài tập tự kiểm tra có lời giải

### Bài 1: Cùng hash, khác khóa

A và B có hashCode bằng 7 nhưng equals false. Put cả hai vào HashMap có bắt buộc chỉ giữ một entry không?

**Lời giải:** không. Va chạm không phải bằng nhau. Map giữ hai ánh xạ nếu hai khóa khác nhau theo hợp đồng.

### Bài 2: Khác tham chiếu, cùng khóa

A và A2 khác đối tượng, equals true và có cùng hashCode. Put A rồi put A2 có giá trị mới. Size và giá trị theo A thế nào?

**Lời giải:** vẫn một ánh xạ cho khóa logic đó; get bằng A cho giá trị mới. Không cần cùng tham chiếu để cập nhật.

### Bài 3: Bucket và hash

Với bảng 16 ô, hai hash đã trộn 1 và 17 đều vào bucket nào? Có đủ để nói hai khóa bằng nhau không?

**Lời giải:** cùng bucket 1 vì dùng mặt nạ 15. Không đủ; hash đầy đủ còn khác nhau và khóa cần có quan hệ nhận diện hợp lệ.

### Bài 4: Một nửa hợp đồng

Một lớp ghi đè equals để hai mã giống nhau là bằng nhau, nhưng hashCode còn xét tên hiển thị có thể khác. Có an toàn không?

**Lời giải:** không nếu tên làm hai đối tượng bằng nhau có hashCode khác. Cần đồng bộ các thành phần và quy tắc của hashCode với equals.

### Bài 5: Khóa bị sửa

Một khóa dùng id trong equals/hashCode, đã được put khi id là 1 rồi đổi id thành 17. Có được dựa vào việc vẫn cầm đúng tham chiếu để get chắc thành công không?

**Lời giải:** không. Hash tính ở thời điểm tra có thể không khớp đường lưu ban đầu. Đây là thiết kế khóa thay đổi trong khi làm khóa, không có bảo đảm sử dụng bình thường.

### Bài 6: Giá trị null

Map có K → null. Get(K) và remove(K) đều trả null. Có thể kết luận K chưa từng tồn tại không?

**Lời giải:** không. Get có thể đã tìm đúng entry có value null; remove có thể đã xóa entry ấy. Khi cần biết tồn tại, phải xem thông tin khóa thích hợp.

### Bài 7: Khóa ghép

Hai tổ chức có cùng customerId 42. Nếu chỉ dùng customerId làm khóa, một giá trị bị thay sau put thứ hai. HashMap có vi phạm khóa duy nhất không?

**Lời giải:** không. Mô hình khóa đang coi hai thực thể là cùng khóa. Nếu cần phân biệt theo tổ chức, dùng khóa ghép phù hợp như CustomerKey.

### Bài 8: Kiểm thử hash

Một kiểm thử yêu cầu mọi khóa khác nhau có hashCode khác nhau. Điều này có đúng hợp đồng hashCode không?

**Lời giải:** không. Hai khóa khác vẫn được phép trùng hash. Kiểm thử nên yêu cầu các khóa bằng nhau có cùng hash và xác nhận map xử lý các khóa khác, kể cả va chạm, đúng kết quả.

## 16. Tài liệu đối chiếu

- [HashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): hợp đồng lớp và các thao tác.
- [Object Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): equals và hashCode.
- [Map Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): tính duy nhất của khóa, null và giới hạn với khóa thay đổi được.
- [HashMap trong OpenJDK 17u](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/HashMap.java): đối chiếu hash, getNode, putVal và removeNode.

Hash giúp tìm vùng ứng viên; equals giúp nhận diện đúng khóa logic. Put, get và remove chỉ phối hợp hiệu quả khi hai phương thức của khóa thống nhất với nhau và thông tin nhận diện được giữ ổn định trong lúc khóa nằm trong map.
