# Vì sao `hashCode()` không bắt buộc giữ nguyên giữa các lần chạy chương trình?

## 1. Phát biểu đúng của hợp đồng

Trong Java, một đối tượng có thể trả về cùng mã băm nhiều lần khi ứng dụng đang chạy, nhưng mã băm đó **không bắt buộc phải giữ nguyên sau khi kết thúc và chạy lại ứng dụng**.

Tài liệu `java.lang.Object.hashCode()` (Java SE 17) nêu ba ràng buộc chính:

1. **Nhất quán trong một lần thực thi:** Khi gọi `hashCode()` nhiều lần trên cùng đối tượng trong **một lần chạy ứng dụng Java**, phương thức phải trả về cùng một số nguyên **miễn là thông tin được dùng trong các phép so sánh `equals` của đối tượng không thay đổi**. Đây không phải cam kết bất biến khi nội dung dùng để xác định equality đã đổi.
2. **Tương thích với `equals()`:** Nếu `a.equals(b)` là `true` thì `a.hashCode() == b.hashCode()` bắt buộc là `true`.
3. **Cho phép va chạm:** Nếu `a.equals(b)` là `false`, Java **không bắt buộc** hai hash code khác nhau. Hai đối tượng không bằng nhau vẫn có thể cùng mã băm.

Sau các ràng buộc trên, tài liệu còn nói rõ rằng số nguyên do `hashCode` trả về **không cần duy trì nhất quán từ một lần thực thi ứng dụng sang một lần thực thi khác**.

Có thể ghi nhớ bằng hai dòng:

- **Trong cùng lần chạy + dữ liệu equality không đổi:** cùng đối tượng ⇒ cùng mã băm.
- **Qua lần chạy khác:** bản thân contract chung của `Object` **không yêu cầu** mã băm cũ phải xuất hiện lại.

Chữ “không yêu cầu” rất quan trọng. Nó **không có nghĩa** Java bắt buộc mỗi lần khởi động phải sinh hash mới. Một class có thể cho cùng mã băm giữa nhiều lần chạy vì thuật toán của nó cố định; điều ấy vẫn hợp lệ. Một class khác có thể cho hash khác mà vẫn tuân thủ contract chung.

## 2. “Một lần chạy” và “hai lần chạy” khác nhau ở đâu?

Ví dụ tình huống:

- Lúc 9 giờ, ứng dụng khởi động; tạo đối tượng `UserKey("U-42")` và gọi `hashCode()`.
- Trong tiến trình đó, ứng dụng gọi lại `hashCode()` nhiều lần mà không thay đổi dữ liệu được dùng trong `equals`.
- Ứng dụng dừng hoàn toàn.
- Lúc 10 giờ, ứng dụng được khởi động lại; tạo một đối tượng mới cũng biểu diễn `UserKey("U-42")` và gọi `hashCode()`.

Hợp đồng yêu cầu các lần gọi thuộc **bước thứ hai** nhất quán. Hợp đồng chung **không buộc** kết quả lúc 10 giờ trùng với kết quả lúc 9 giờ.

Tại sao? `hashCode` được thiết kế như một số nguyên hỗ trợ cấu trúc dữ liệu dựa trên hash **trong lúc thực thi**, không phải định danh lưu trữ vĩnh viễn. Java không công bố một thuật toán hash duy nhất bắt mọi class phải dùng. Cách triển khai của class và môi trường thực thi có thể quyết định giá trị số cụ thể.

Bởi vậy, không nên suy luận “tôi vừa chạy hai lần đều được cùng hash nên Java đảm bảo mọi lần sau cũng vậy”. Quan sát lặp lại trong một môi trường là **bằng chứng về cách triển khai hiện tại**, chưa đủ để chứng minh contract chung.

## 3. Ví dụ Java 17: hash phụ thuộc một giá trị được tạo lúc khởi động

Class sau so sánh khóa phiên theo `id`. Nó sinh một số `RUN_SALT` đúng một lần khi class được khởi tạo trong lần chạy ứng dụng. Trong lần chạy đó, `RUN_SALT` không đổi; mỗi đối tượng có cùng `id` luôn có cùng mã băm. Nếu chạy lại chương trình, giá trị ngẫu nhiên có thể khác nên hash của cùng `id` cũng có thể khác.

```java
import java.security.SecureRandom;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class HashAcrossRunsDemo {
    static final class SessionKey {
        private static final int RUN_SALT = new SecureRandom().nextInt();

        private final String id;

        SessionKey(String id) {
            this.id = Objects.requireNonNull(id, "id");
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof SessionKey that)) {
                return false;
            }
            return id.equals(that.id);
        }

        @Override
        public int hashCode() {
            return 31 * id.hashCode() + RUN_SALT;
        }
    }

    public static void main(String[] args) {
        SessionKey first = new SessionKey("U-42");
        SessionKey second = new SessionKey("U-42");
        Set<SessionKey> keys = new HashSet<>();
        keys.add(first);

        int before = first.hashCode();
        int after = first.hashCode();

        System.out.println(first.equals(second));
        System.out.println(before == after);
        System.out.println(first.hashCode() == second.hashCode());
        System.out.println(keys.contains(second));
    }
}
```

Lưu mã bằng UTF-8 vào tệp `HashAcrossRunsDemo.java` và chạy:

```bash
javac -encoding UTF-8 HashAcrossRunsDemo.java
java HashAcrossRunsDemo
```

**Đầu ra xác định của ví dụ:**

```text
true
true
true
true
```

Giải thích:

1. `first.equals(second)` trả về `true` vì hai đối tượng có cùng `id`.
2. `before == after` là `true` vì `id` và `RUN_SALT` không đổi trong lần chạy hiện tại.
3. Hai đối tượng bằng nhau có cùng hash vì biểu thức tính hash dùng cùng `id` và cùng `RUN_SALT`.
4. `HashSet.contains(second)` trả `true` dù tập hợp lưu đối tượng `first`, nhờ hợp đồng `equals`/`hashCode` được giữ.

Chạy lại `java HashAcrossRunsDemo` vẫn cho **bốn dòng `true`**, nhưng giá trị số nguyên nội bộ của `hashCode()` **có thể** đã khác. Ví dụ cố ý không in số ngẫu nhiên, vì không thể dự đoán một giá trị cụ thể làm đầu ra chuẩn. Dùng `SecureRandom` ở đây chỉ để minh họa rằng việc chọn một tham số theo lần khởi động vẫn có thể đáp ứng contract; nó **không biến `hashCode` thành mã băm mật mã** hay kỹ thuật quản lý phiên an toàn.

Một khả năng nhỏ là hai lần khởi động ngẫu nhiên nhận cùng `RUN_SALT`. Điều đó không phủ định bài học: Java cho phép cả trùng lẫn khác giữa các lần chạy.

### Vì sao class có thể thêm “salt” mà vẫn đúng?

Vì contract chỉ cần:

- Trong một lần chạy, cùng đối tượng và cùng dữ liệu equality ⇒ cùng kết quả.
- Hai đối tượng có cùng `id` ⇒ cùng kết quả hash.
- Không cần đảm bảo hai `id` khác nhau nhận hai hash khác nhau.

Biểu thức `31 * id.hashCode() + RUN_SALT` thỏa ba điều kiện. Số 31 chỉ là lựa chọn của ví dụ, không phải hệ số Java yêu cầu cho mọi class. Phép cộng/tràn số nguyên `int` theo ngữ nghĩa Java không làm sai các tính chất nói trên.

## 4. Đừng hiểu thành “mọi hashCode đều thay đổi khi restart”

Các kiểu dữ liệu cụ thể **có thể công bố hợp đồng mạnh hơn** hợp đồng chung của `Object`.

Ví dụ quan trọng là `String.hashCode()`. Javadoc của `String` định nghĩa thuật toán dựa trên các ký tự trong chuỗi, sử dụng lũy thừa của 31 theo thứ tự ký tự. Vì thế, cùng nội dung chuỗi sẽ cho cùng mã băm theo đặc tả của `String`, kể cả khi tạo chuỗi ở những lần chạy khác nhau trên môi trường tuân thủ API.

Ví dụ:

```java
String a = "java";
String b = new String("java");

System.out.println(a.equals(b));              // true
System.out.println(a.hashCode() == b.hashCode()); // true
```

Đây là **đoạn mã minh họa đặt trong phương thức**, không phải một tệp Java độc lập. Việc hash bằng nhau ở ví dụ này có thể suy ra từ hợp đồng `equals` và `hashCode` của `String`; và do `String.hashCode` được đặc tả theo nội dung, kết quả số cũng được xác định theo chuỗi. Không được từ đó kết luận rằng **mọi class** có thuật toán cố định tương tự.

Bảng phân biệt:

| Đối tượng/phương thức | Có thể dựa vào điều gì? | Không nên suy ra điều gì? |
| --- | --- | --- |
| `Object.hashCode()` (quy tắc chung) | Nhất quán trong lần chạy nếu dữ liệu equality không đổi; bằng nhau thì cùng hash | Giá trị số cụ thể phải trùng giữa mọi lần chạy |
| `String.hashCode()` | Thuật toán được Javadoc đặc tả theo nội dung chuỗi | Hash là duy nhất cho mỗi chuỗi; hai chuỗi khác nhau vẫn có thể trùng hash |
| Class tự viết với thuật toán hoàn toàn dựa trên dữ liệu ổn định | Có thể chủ động cung cấp hash ổn định qua lần chạy | Tính ổn định đó tự động áp dụng cho mọi class khác |
| Class dùng salt riêng theo lần khởi động | Có thể thay hash giữa các lần chạy mà vẫn giữ contract trong một lần chạy | Hash sẽ **chắc chắn** khác mỗi lần |
| `System.identityHashCode(obj)` | Lấy mã băm theo cơ chế identity, bất kể class override `hashCode` ra sao | Giá trị phải dựa trực tiếp trên địa chỉ bộ nhớ hoặc có tính bền vững qua khởi động |

**Phân biệt bảo đảm của Java và bảo đảm riêng của API.** Nếu cần dựa trên một giá trị hash ổn định vì lý do giao thức/lưu trữ, phải có đặc tả cho **chính thuật toán và biểu diễn đầu vào**. Hợp đồng mặc định của `Object.hashCode` chưa đủ.

## 5. `Object.hashCode` và `System.identityHashCode` không phải mã định danh bền vững

Khi một class không override `hashCode`, nó sử dụng implementation kế thừa từ `Object`. Hành vi này gắn với nhận diện đối tượng trong môi trường thực thi; không nên coi số nguyên nhận được là khóa định danh lưu trữ.

`System.identityHashCode(x)` cung cấp giá trị hash theo identity ngay cả khi class của `x` override `hashCode()`. Tuy nhiên:

- Hai đối tượng khác nhau **vẫn có thể** có cùng identity hash code; số nguyên hash không phải mã định danh duy nhất tuyệt đối.
- Không có bảo đảm mã hash identity chính là địa chỉ RAM hoặc là số thứ tự cấp phát.
- Không có bảo đảm một đối tượng được tái tạo sau restart sẽ có hash identity cũ.
- Nếu `x` và `y` bằng nhau theo giá trị do override `equals`, `System.identityHashCode(x)` và `System.identityHashCode(y)` không nhất thiết bằng nhau. Bởi vậy **không dùng `System.identityHashCode` làm implementation cho `hashCode()` của một class có value equality**, trừ khi có cơ chế khác bảo đảm tương thích.

Cả `Object.hashCode` lẫn identity hash đều phù hợp cho những nhu cầu nhất định trong quá trình chạy, nhưng không thay thế được ID nghiệp vụ, ID cơ sở dữ liệu hoặc khóa được quản lý theo một hợp đồng lâu dài.

## 6. Hệ quả khi lưu hash xuống cơ sở dữ liệu, tệp hoặc cache ngoài JVM

Một lỗi thiết kế thường gặp là lưu `object.hashCode()` như “mã cố định” của bản ghi:

```java
// Ví dụ thiết kế không an toàn khi cần định danh bền vững:
int persistedId = customer.hashCode();
```

Dòng này chỉ là đoạn mã minh họa, không phải chương trình độc lập. Nếu `customer.hashCode()` phụ thuộc implementation hoặc dữ liệu có thể thay đổi, giá trị lưu có thể không còn thích hợp trong lần chạy sau. Ngay cả khi thuật toán ổn định, **hai đối tượng khác nhau vẫn có thể cùng hash**; vì vậy hash code không đáp ứng yêu cầu định danh duy nhất.

Các tình huống rủi ro:

1. **Lưu khóa database bằng hash code:** Có thể gây va chạm và không bảo đảm ổn định khi class/JDK thay đổi.
2. **Ghi hash vào tệp rồi so sánh sau khi restart:** Hai giá trị có thể khác dù dữ liệu nghiệp vụ giống hệt nhau.
3. **Chia shard hoặc phân phối dữ liệu bằng `Object.hashCode()` tùy ý:** Nếu các tiến trình hoặc phiên bản code tính hash khác nhau, cùng khóa logic có thể được gán sang vị trí khác. Nếu chia shard cần tính ổn định, giao thức phân phối phải đặc tả thuật toán hash và dạng chuẩn của khóa.
4. **Tra cứu bản ghi dựa vào hash lưu từ lần chạy trước:** Hash có thể thay đổi theo execution hoặc phiên bản; ngay cả khi không đổi thì collision vẫn khiến phép tìm kiếm thiếu an toàn.
5. **Xây checksum hoặc chữ ký bảo mật từ `hashCode()`:** Mã băm `int` của `Object` không phải digest mật mã, không bảo đảm chống đụng độ và không xác nhận tính toàn vẹn chống giả mạo.

Nếu muốn lưu định danh, hãy dùng một ID được quy định rõ (chẳng hạn khóa nghiệp vụ hoặc UUID phù hợp với thiết kế). Nếu muốn phát hiện thay đổi dữ liệu, chọn thuật toán digest phù hợp nhu cầu cùng quy tắc mã hóa/serialize ổn định; nếu cần chống giả mạo, xem xét HMAC hoặc chữ ký số với cơ chế quản lý khóa phù hợp. Những mục tiêu này khác với mục tiêu của `Object.hashCode()`.

## 7. `HashMap` và `HashSet` cần gì từ hash trong một lần chạy?

`HashMap` và `HashSet` sử dụng hash để tổ chức và tìm phần tử. Trong một lần thực thi, nếu một khóa được chèn và sau đó tìm lại bằng một khóa khác **bằng nhau theo `equals`**, cả hai phải cho cùng hash để bảo toàn ngữ nghĩa tra cứu.

Không cần các bucket nội bộ hoặc hash trước/sau restart trùng nhau. Khi khởi động ứng dụng mới, collection trong bộ nhớ cũng được xây dựng lại. Mỗi lần thêm khóa vào collection mới, cơ chế hash của lần chạy đó được áp dụng nhất quán.

Ví dụ, class `SessionKey` phía trên hoàn toàn có thể dùng làm khóa trong `HashMap` của một lần chạy. Nếu ứng dụng dừng rồi khởi động lại, việc dựng một `HashMap` mới từ các khóa nghiệp vụ vẫn hợp lệ dù salt/hash mới khác. Điều quan trọng là việc phục hồi dữ liệu dựa trên **ID thật hoặc dữ liệu giá trị**, không dựa trên bucket cũ hay con số hash cũ.

### Lỗi khác cần tách bạch: đổi dữ liệu tham gia equality

Nếu một khóa mutable được thêm vào `HashSet` rồi người dùng sửa trường tham gia `equals`/`hashCode`, mã băm **trong cùng lần chạy** có thể đổi và phép `contains` có thể thất bại. Đây không phải vấn đề “hash không ổn định qua restart”; đây là vấn đề **biến đổi trạng thái khi khóa đang nằm trong hash collection**.

Nên thiết kế những trường quyết định equality của khóa là bất biến, hoặc đảm bảo chúng không đổi trong suốt thời gian khóa được dùng trong collection.

## 8. Những nhận định dễ nhầm

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “Với cùng đối tượng, gọi `hashCode` hai lần trong một lần chạy phải cho cùng số nếu dữ liệu equality không đổi.” | **Đúng** | Đúng contract nhất quán. |
| “`hashCode` của cùng giá trị phải giữ nguyên qua mọi lần khởi động JVM.” | **Sai nếu phát biểu như quy tắc chung** | `Object` không yêu cầu vậy; class cụ thể có thể công bố mạnh hơn. |
| “Java bắt buộc hash thay đổi mỗi lần restart.” | **Sai** | Không yêu cầu giống nhau **cũng không yêu cầu khác nhau**. |
| “Nếu hai đối tượng bằng nhau theo `equals` thì hash bằng nhau.” | **Đúng, bắt buộc** | Dù class chọn thuật toán nào. |
| “Nếu hai hash bằng nhau thì hai đối tượng bằng nhau.” | **Sai** | Hash collision được phép. |
| “`String.hashCode` có thuật toán theo nội dung đã đặc tả.” | **Đúng** | Đây là cam kết riêng của `String`, không phủ lên mọi class. |
| “`System.identityHashCode` là địa chỉ bộ nhớ.” | **Không có bảo đảm** | API không hứa quan hệ trực tiếp như vậy. |
| “Có thể dùng hash code như ID duy nhất trong database.” | **Không an toàn** | Vừa có khả năng va chạm vừa thiếu bảo đảm bền vững chung. |
| “Một class có thể thêm salt cố định cho mỗi lần chạy khi tính hash.” | **Có thể đúng** | Nếu bảo đảm nhất quán trong lần chạy và tương thích `equals`. |

## 9. Quy trình chọn kỹ thuật hash theo nhu cầu thực tế

**Khi cần `equals`/`hashCode` cho Java collection trong bộ nhớ:**

1. Định nghĩa rõ những trường quyết định hai đối tượng bằng nhau.
2. Đảm bảo hai đối tượng bằng nhau cho cùng hash, kể cả khi chúng là hai instance khác nhau.
3. Giữ kết quả ổn định trong thời gian dữ liệu equality không đổi.
4. Chọn phân bố hash hợp lý để tránh nhiều collision không cần thiết.
5. Tránh đột biến trường equality khi đối tượng đang là hash key.

**Khi cần mã ổn định qua restart, qua phiên bản dịch vụ hoặc giữa máy khác nhau:**

1. Xác định rõ mục đích: định danh, phân vùng, checksum hay bảo mật.
2. Chọn thuật toán và dạng chuẩn hóa đầu vào được đặc tả tường minh cho mục đích đó.
3. Quy định encoding, thứ tự byte, cách serialize và versioning (nếu dữ liệu phức tạp).
4. Thiết kế cách xử lý va chạm/di chuyển dữ liệu nếu cần.
5. Kiểm thử qua nhiều tiến trình và phiên bản, **không phụ thuộc ngầm vào `Object.hashCode()`**.

Với dữ liệu cần so sánh giữa các tiến trình, ngay cả khi có thuật toán hash ổn định, một mã băm nhỏ vẫn có nguy cơ collision; khi tính đúng đòi hỏi phân biệt tuyệt đối, phải kết hợp kiểm tra khóa/dữ liệu đầy đủ hoặc một định danh có bảo đảm phù hợp hơn.

## 10. Câu hỏi tự luyện

**Câu 1.** Chạy một ứng dụng hai lần, cùng tạo object đại diện cho mã `"A-01"`. Lần đầu được hash `123`, lần sau được hash `456`. Có thể kết luận vi phạm `Object.hashCode()` không?

**Đáp án:** Không thể kết luận như vậy. Contract chung không yêu cầu cùng hash giữa hai lần chạy. Muốn xác định đúng/sai phải kiểm tra contract cụ thể của class và các điều kiện liên quan, nhất là trong **mỗi** lần chạy, các đối tượng bằng nhau có cùng hash và hash không tự thay đổi khi dữ liệu equality không đổi.

**Câu 2.** Chạy hai lần và nhận hash `123` ở cả hai lần. Có thể kết luận Java bảo đảm các lần chạy sau vẫn là `123` không?

**Đáp án:** Không. Hai quan sát trùng nhau không tạo thành bảo đảm chung. Chỉ khi API cụ thể định nghĩa thuật toán/đầu vào và các điều kiện phù hợp mới có cơ sở dựa vào kết quả qua các lần chạy.

**Câu 3.** Trong **một lần chạy**, hai đối tượng `UserKey("U-42")` trả `true` khi gọi `equals`, nhưng hash lần lượt là `101` và `202`. Có hợp lệ không?

**Đáp án:** Không. Đây là vi phạm ràng buộc bắt buộc “bằng nhau theo `equals` thì có cùng hash code”.

**Câu 4.** Một class lưu mã băm của `String code` bằng `code.hashCode()`. Vì `String.hashCode()` được đặc tả, có thể dùng số đó làm khóa chính duy nhất cho mọi chuỗi không?

**Đáp án:** Không. Thuật toán xác định không đồng nghĩa với tính duy nhất. Hai chuỗi khác nhau có thể có cùng hash. Khóa chính phải xử lý vấn đề uniqueness theo yêu cầu dữ liệu.

**Câu 5.** Một ứng dụng lưu `hashCode()` của các object để phân phối bản ghi tới máy chủ. Sau deploy, logic triển khai hash thay đổi nhưng equality vẫn giữ nguyên. Điều gì có thể xảy ra?

**Đáp án:** Hash và vị trí phân vùng của cùng khóa logic có thể đổi, dù implementation mới vẫn đúng `Object` contract. Phân phối ổn định qua triển khai cần giao thức băm được kiểm soát và cơ chế di chuyển dữ liệu, không dựa vào hash code triển khai tùy ý.

## 11. Ghi nhớ

- `Object.hashCode()` **phải nhất quán trong một lần chạy** khi dữ liệu dùng trong `equals` không đổi.
- `a.equals(b) == true` ⇒ `a.hashCode() == b.hashCode()`, nhưng cùng hash **không** chứng minh hai đối tượng bằng nhau.
- **Không có yêu cầu giữ cùng giá trị hash giữa các lần chạy chương trình**; cũng không có yêu cầu bắt buộc phải thay đổi.
- `String.hashCode()` là ví dụ một API cụ thể công bố thuật toán theo nội dung; luôn phân biệt cam kết của class cụ thể với contract chung.
- `hashCode()` phục vụ equality và cấu trúc dữ liệu dựa trên hash trong bộ nhớ, **không thay thế** ID bền vững, checksum có đặc tả hay mã băm mật mã.
- Đừng nhầm lỗi do *restart* với lỗi do thay đổi trường tham gia equality của một khóa đang nằm trong `HashMap`/`HashSet`.

Tài liệu đối chiếu: [`Object.hashCode()` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#hashCode()), [`String.hashCode()` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#hashCode()), [`System.identityHashCode()` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#identityHashCode(java.lang.Object)) và [`HashMap` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).
