# Sao chép phòng vệ ở biên constructor, accessor và phương thức

## 1. Vì sao một trường private vẫn có thể bị sửa từ bên ngoài?

Giả sử một lớp giữ danh sách điểm trong `private final int[] scores` và yêu cầu mọi điểm luôn nằm trong khoảng 0–100. Nếu constructor giữ thẳng mảng do bên gọi đưa vào, bên gọi vẫn còn tham chiếu đến mảng đó. Họ có thể sửa một phần tử sau khi constructor kết thúc, bỏ qua mọi phương thức kiểm tra của lớp.

Một getter trả thẳng trường `scores` cũng mở đường sửa tương tự từ hướng ngược lại. `private` hạn chế truy cập trường theo tên; nó không xóa những tham chiếu khác đến cùng đối tượng mảng.

**Sao chép phòng vệ (defensive copying)** là tạo dữ liệu tách biệt tại ranh giới sở hữu để bên ngoài không tùy ý làm thay đổi trạng thái mà đối tượng cần bảo vệ. Mục tiêu không chỉ là “có một mảng mới”, mà là giữ các điều kiện của lớp luôn đúng.

Mảng Java là đối tượng có thể thay đổi phần tử; biến mảng giữ tham chiếu. Clone một mảng tạo mảng mới, nhưng với mảng tham chiếu chỉ chép các tham chiếu phần tử. [Quy tắc mảng và clone trong JLS](https://docs.oracle.com/javase/specs/jls/se25/html/jls-10.html)

## 2. Ba biên cần kiểm soát

| Biên | Nguy cơ dùng chung | Cách suy nghĩ về bản sao |
| --- | --- | --- |
| Constructor nhận mảng | Đối tượng giữ mảng mà bên gọi còn sửa được | Nhận dữ liệu nhưng giữ một bản do lớp sở hữu |
| Accessor/getter trả mảng | Bên gọi nhận được đường sửa trạng thái nội bộ | Trả bản sao hoặc cung cấp thao tác đọc không lộ mảng |
| Phương thức nhận/trả mảng | Giữ lại, sửa hoặc chuyển tiếp dữ liệu sai hợp đồng | Xác định rõ phương thức mượn, nhận quyền sở hữu hay trả dữ liệu mới |

Hai hướng đầu vào và đầu ra độc lập. Chỉ sửa constructor mà getter vẫn trả trường nội bộ thì đối tượng vẫn bị sửa từ ngoài. Chỉ sửa getter mà constructor giữ tham chiếu đầu vào thì bên gọi ban đầu vẫn có đường thay đổi trạng thái.

```text
đầu vào của bên gọi --sao chép--> dữ liệu lớp sở hữu
dữ liệu lớp sở hữu --sao chép--> kết quả bên gọi được phép sửa
```

`final` trên trường mảng chỉ ngăn gán lại trường đó sang mảng khác sau khi đã được khởi tạo đúng quy tắc. Nó không cấm `scores[0] = ...`. Một lớp muốn giữ trạng thái bất biến phải kiểm soát cả nội dung mảng và mọi đường làm lộ nội dung có thể thay đổi.

## 3. Constructor: kiểm tra đúng dữ liệu sẽ được giữ

Mẫu giữ nguyên tham chiếu sau đây không bảo vệ được trạng thái:

```java
// Minh họa constructor chưa an toàn của một lớp giữ int[].
ScoreCard(int[] input) {
    validate(input);
    this.scores = input;
}
```

`validate` ở đây là thao tác kiểm tra do ứng dụng cung cấp. Dù kiểm tra đúng, bên gọi vẫn sửa được mảng sau đó. Còn nếu đổi dòng cuối thành `this.scores = input.clone()` nhưng vẫn kiểm tra nguồn trước, dữ liệu có thể bị một luồng khác thay đổi giữa lúc kiểm tra và lúc sao chép.

Mẫu phù hợp hơn là:

1. Kiểm tra `null` và giới hạn cấu trúc không thay đổi như độ dài.
2. Tạo bản sao do lớp sở hữu.
3. Kiểm tra nội dung chính bản sao đó.
4. Chỉ gán vào trạng thái được công bố khi toàn bộ dữ liệu đã hợp lệ.

Kiểm tra độ dài trước khi cấp phát có ích khi API nhận dữ liệu không được tin cậy về kích thước. Độ dài của một đối tượng mảng không thay đổi sau khi tạo. Ngược lại, kiểm tra giá trị phần tử cần thực hiện trên bản mà lớp sẽ giữ.

Điều này bảo đảm các điểm được lưu đã qua kiểm tra. Nó không tự bảo đảm nguồn đã được chụp nhất quán trong lúc một luồng khác đang ghi; yêu cầu về ảnh chụp đồng thời cần hợp đồng riêng.

## 4. Accessor: trả dữ liệu đọc được mà không lộ quyền sửa

Đối với `int[]`, một accessor có thể trả `scores.clone()`. Bên gọi được quyền thay phần tử trong kết quả nhưng không thay mảng riêng của đối tượng.

Nếu bên gọi chỉ cần một điểm, trả `int scoreAt(int index)` tránh tạo bản sao toàn mảng. Nếu cần đếm, trả số lượng. Thiết kế API theo nhu cầu đọc thực tế có thể giảm cả lượng dữ liệu lộ ra và chi phí sao chép.

Không tạo một bản sao duy nhất rồi dùng nó làm kết quả getter cho mọi lần gọi. Nếu mảng kết quả được lưu lại và chia sẻ, một bên gọi có thể sửa dữ liệu mà các bên gọi sau nhìn thấy. Một bản sao đầu ra chỉ thật sự tách biệt theo hợp đồng khi lớp không tiếp tục chia sẻ chính mảng có thể thay đổi đó với các bên không liên quan.

## 5. Ví dụ hoàn chỉnh: bảo vệ cả đầu vào, đầu ra và phương thức

Lớp `ScoreCard` dưới đây giữ những điểm hợp lệ, trả bản sao ở accessor và tạo đối tượng mới khi cần thay một điểm. Hàm `sortedCopy` thể hiện một hợp đồng phương thức khác: không sửa mảng nhận vào, trả một mảng đã sắp xếp mới cho bên gọi sở hữu.

Lưu thành `DefensiveArrayBoundaryDemo.java`, dùng Java 17+ và không cần thư viện ngoài:

```java
import java.util.Arrays;
import java.util.Objects;

public class DefensiveArrayBoundaryDemo {
    static final class ScoreCard {
        private static final int MAX_SCORES = 10_000;
        private final int[] scores;

        ScoreCard(int[] input) {
            Objects.requireNonNull(input, "input");
            if (input.length > MAX_SCORES) {
                throw new IllegalArgumentException("Too many scores");
            }
            int[] snapshot = input.clone();
            for (int score : snapshot) {
                if (score < 0 || score > 100) {
                    throw new IllegalArgumentException("Score out of range");
                }
            }
            this.scores = snapshot;
        }

        int[] scores() {
            return scores.clone();
        }

        int scoreAt(int index) {
            return scores[index];
        }

        ScoreCard withScore(int index, int score) {
            Objects.checkIndex(index, scores.length);
            int[] changed = scores.clone();
            changed[index] = score;
            return new ScoreCard(changed);
        }
    }

    static int[] sortedCopy(int[] input) {
        int[] result = Objects.requireNonNull(input, "input").clone();
        Arrays.sort(result);
        return result;
    }

    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        int[] supplied = {80, 90};
        ScoreCard card = new ScoreCard(supplied);
        supplied[0] = 0;
        check(card.scoreAt(0) == 80, "constructor leaked input");
        System.out.println("after-input-change=" + Arrays.toString(card.scores()));

        int[] returned = card.scores();
        returned[1] = 1;
        check(card.scoreAt(1) == 90, "accessor leaked state");
        check(returned != card.scores(), "accessor reused mutable array");
        System.out.println("after-accessor-change="
                + Arrays.toString(card.scores()));

        ScoreCard updated = card.withScore(0, 100);
        check(card.scoreAt(0) == 80, "method changed original");
        check(updated.scoreAt(0) == 100, "method lost update");
        System.out.println("original=" + Arrays.toString(card.scores()));
        System.out.println("updated=" + Arrays.toString(updated.scores()));

        int[] unsorted = {3, 1, 2};
        int[] sorted = sortedCopy(unsorted);
        check(Arrays.equals(unsorted, new int[] {3, 1, 2}), "method changed input");
        check(Arrays.equals(sorted, new int[] {1, 2, 3}), "wrong sorted result");
        check(sorted != unsorted, "method returned input alias");
        System.out.println("method-input=" + Arrays.toString(unsorted));
        System.out.println("method-result=" + Arrays.toString(sorted));

        try {
            card.withScore(0, -1);
            throw new AssertionError("invalid score accepted");
        } catch (IllegalArgumentException expected) {
            check(card.scoreAt(0) == 80, "failed update damaged original");
            System.out.println("invalid-update=rejected");
        }
        System.out.println("ALL CHECKS PASS");
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 DefensiveArrayBoundaryDemo.java
java DefensiveArrayBoundaryDemo
```

Đầu ra:

```text
after-input-change=[80, 90]
after-accessor-change=[80, 90]
original=[80, 90]
updated=[100, 90]
method-input=[3, 1, 2]
method-result=[1, 2, 3]
invalid-update=rejected
ALL CHECKS PASS
```

Hàm `check` ném `AssertionError` trực tiếp nếu điều kiện sai, nên không cần bật `-ea`.

### Constructor và accessor đang bảo vệ hai đường khác nhau

Sau `new ScoreCard(supplied)`, sửa `supplied[0]` không làm đổi điểm đã giữ. Đó là bằng chứng về việc không giữ chung mảng đầu vào.

Sửa `returned[1]` cũng không làm thay đổi điểm trong `card`. Đó là bằng chứng accessor không trả đường sửa mảng nội bộ. Hai kiểm tra đều cần thiết vì đạt một kiểm tra không suy ra kiểm tra kia cũng đạt.

### Phương thức withScore không sửa đối tượng cũ

`withScore` tạo mảng trung gian, thay một ô, rồi đi qua constructor để kiểm tra dữ liệu của đối tượng mới. Nếu điểm mới không hợp lệ, việc tạo đối tượng mới thất bại nhưng `card` cũ vẫn nguyên vẹn.

Ví dụ ưu tiên đường xử lý rõ ràng: có một lần clone để tạo dữ liệu cập nhật và một lần clone trong constructor. Có thể giảm sao chép thừa bằng một đường nội bộ chỉ nhận dữ liệu thực sự thuộc quyền sở hữu của lớp, nhưng đường đó phải kín và có điều kiện rõ ràng. Không mở một constructor công khai “tin cậy mảng này” rồi để bên ngoài vượt qua hợp đồng.

### Phương thức sortedCopy chuyển quyền sở hữu kết quả mới

`Arrays.sort` sửa chính mảng được đưa vào. Hàm `sortedCopy` clone trước, chỉ sắp xếp bản sao, rồi trả nó. [Các thao tác sort/copy trong Arrays](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html)

Hàm không giữ tham chiếu đến mảng kết quả sau khi trả về. Vì vậy không cần clone thêm một lần ở dòng `return`: bên gọi nhận một mảng mới mà hàm không còn dùng làm trạng thái nội bộ.

## 6. Phương thức nhận mảng: không phải lúc nào cũng cần clone

Quyết định dựa trên hợp đồng, không dựa riêng vào việc tham số có dấu `[]`.

| Phương thức làm gì? | Có cần sao chép phòng vệ không? |
| --- | --- |
| Giữ tham số vào một trường để dùng về sau | Thường cần nếu bên gọi vẫn sở hữu và sửa được dữ liệu |
| Đưa tham số vào tác vụ chạy sau | Cần xác định dữ liệu phải cố định từ lúc nào; không chỉ giữ nguyên tham chiếu |
| Sắp xếp và công khai hợp đồng sửa mảng tại chỗ | Không clone nếu mục đích chính là sửa mảng bên gọi cung cấp |
| Chỉ đọc đồng bộ, không giữ và không chuyển tham chiếu ra ngoài | Có thể mượn mảng nếu hợp đồng cho phép và dữ liệu được ổn định trong thời gian gọi |
| Trả kết quả mới, không lưu lại trong lớp | Có thể giao trực tiếp mảng mới cho bên gọi |

Ví dụ một phương thức `sortInPlace(int[] values)` có thể chủ ý thay đổi đầu vào; clone bên trong rồi không chép kết quả trở lại sẽ làm sai hợp đồng. Ngược lại, tên và tài liệu của `sortedCopy` cần nêu rõ không sửa đầu vào.

Với phương thức chỉ đọc, việc không giữ tham chiếu không bảo đảm an toàn nếu một luồng khác đang ghi đồng thời. Hai bên phải thống nhất thời gian dữ liệu được giữ ổn định. Sao chép không thay thế toàn bộ thiết kế đồng bộ.

### Đặc biệt với tác vụ chạy sau

Giả sử một phương thức nhận mảng rồi đưa lambda vào executor. Nếu lambda mới clone khi nó thực sự chạy, bên gọi có thể đã sửa mảng sau khi phương thức trả về. Bản sao lúc đó phản ánh một thời điểm khác với lúc tiếp nhận.

Nếu hợp đồng yêu cầu giữ dữ liệu từ lúc gọi, hãy tạo bản do phương thức sở hữu ngay tại biên tiếp nhận rồi đưa chính bản đó vào tác vụ. Đồng thời phải xét các giới hạn kích thước, vòng đời và chi phí giữ dữ liệu trong thời gian đợi.

## 7. Mảng tham chiếu: clone mảng ngoài chưa bảo vệ trạng thái phần tử

Đối với `int[]` trong ví dụ, mỗi phần tử là giá trị số nên clone mảng đủ tách nội dung. Với `MutableItem[]`, bản sao mảng chỉ tách các ô tham chiếu.

```text
mảng nội bộ ----> [ref-X] ----> MutableItem X
mảng trả về ----> [ref-X] -----------^
```

Bên gọi không thể dùng mảng trả về để thay ô trong mảng nội bộ, nhưng vẫn có thể sửa `MutableItem X` nếu nhận được tham chiếu và lớp đó có hành vi thay đổi trạng thái.

Có ba hướng thiết kế thường dùng:

- Dùng phần tử bất biến và chỉ sao chép mảng ngoài.
- Tạo bản sao từng phần tử có thể thay đổi theo hợp đồng dữ liệu.
- Trả một biểu diễn đọc hoặc dữ liệu giá trị khác, tránh lộ đối tượng nội bộ có thể sửa.

Sao chép từng phần tử cũng cần áp dụng ở cả đầu vào và đầu ra nếu muốn cách ly trọn vẹn. Không sao chép sâu ở constructor rồi lại trả thẳng các đối tượng phần tử từ getter.

Với `int[][]`, clone mảng ngoài vẫn dùng chung các hàng `int[]`. Cần sao chép từng hàng nếu trạng thái cần bảo vệ bao gồm các số trong hàng. Với đồ thị đối tượng phức tạp, còn phải quyết định giữ hay tách những quan hệ dùng chung và xử lý chu trình; không có một quy tắc clone mảng tự làm hết.

## 8. Record cũng cần hợp đồng cho mảng có thể thay đổi

Record có các trường thành phần `private final`, nhưng không tự làm cho đối tượng được tham chiếu trở nên bất biến. Constructor và accessor mặc định lưu/trả giá trị thành phần; vì vậy record chứa mảng vẫn có thể dùng chung mảng với bên gọi. [Tài liệu Record](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Record.html)

Đoạn khai báo sau minh họa trường hợp **chưa có** sao chép phòng vệ:

```java
record Samples(int[] values) {}
```

Nếu dùng record làm một giá trị có trạng thái mảng cần bảo vệ, cần chủ động thiết kế canonical constructor và accessor để sao chép theo yêu cầu. Tuy nhiên, chỉ thêm clone vào hai nơi đó chưa giải quyết toàn bộ hợp đồng giá trị.

`equals`/`hashCode` mặc định của record đối với thành phần mảng không tự so sánh theo nội dung mảng. Nếu constructor luôn tạo mảng mới, phép dựng lại từ accessor có thể không còn bằng theo cách so sánh mặc định dựa trên tham chiếu mảng. Khi chọn mô hình giá trị theo nội dung, cần thiết kế `equals` và `hashCode` nhất quán, chẳng hạn cùng dựa trên `Arrays.equals`/`Arrays.hashCode` cho `int[]`, hoặc chọn biểu diễn khác phù hợp hơn. [Hợp đồng thành viên của record](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.3)

Không đổi một lớp sang record rồi mặc định rằng mọi yêu cầu sở hữu dữ liệu đã được xử lý.

## 9. Bất biến, tính nhất quán và đồng thời là các yêu cầu khác nhau

Sao chép phòng vệ giúp cắt một đường sửa trạng thái qua tham chiếu dùng chung. Nó không tự cung cấp khóa, không làm một lớp có phương thức thay đổi trạng thái trở thành an toàn luồng, và không bảo đảm bản sao được tạo trong một giao dịch nguyên tử.

Trong constructor ví dụ, mọi điểm ở `snapshot` đều được kiểm tra trước khi lưu. Nếu nguồn bị sửa trong lúc clone, dữ liệu giữ lại vẫn được kiểm tra theo quy tắc 0–100, nhưng có thể không đại diện cho một trạng thái đồng thời nhất quán mà ứng dụng mong muốn.

Đối với dữ liệu có nhiều phần tử liên hệ nhau, như hai cột số phải khớp hoặc giá trị đi kèm phiên bản, cần bảo đảm nguồn ổn định trong quá trình chụp. Giải pháp có thể là cùng dùng khóa bảo vệ, chuyển giao quyền sở hữu rõ ràng hoặc dùng dữ liệu bất biến. Việc chọn giải pháp phụ thuộc vào hợp đồng giữa các thành phần.

Ngay cả phương thức sao chép sâu cũng không tự giải quyết vấn đề này nếu đối tượng con bị thay đổi trong lúc đang được đọc để sao chép.

## 10. Chi phí và lựa chọn API

Sao chép mảng cùng độ dài cần thêm vùng chứa phần tử và công việc tỷ lệ với số phần tử được chép. Sao chép sâu còn tạo thêm đối tượng và có thể giữ một cấu trúc dữ liệu lớn hơn nhiều.

Không trả toàn bộ mảng chỉ để bên gọi đọc một phần tử trong vòng lặp. Nếu mỗi vòng gọi `scores()` một lần, chi phí tạo bản sao có thể lặp lại không cần thiết. Hãy lấy một bản sao cho một lần xử lý hoặc cung cấp phương thức đọc theo chỉ số, tùy nhu cầu.

Những tối ưu như bỏ bản sao đầu vào chỉ hợp lý khi đã có **chuyển quyền sở hữu** thực sự: bên gọi cam kết không còn sử dụng hay sửa mảng và API làm hợp đồng đó rõ ràng. Java không tự thực thi cam kết này bằng kiểu `int[]`, nên không dùng nó như một giả định ngầm ở API công khai thông thường.

Tại biên dữ liệu có thể rất lớn, đặt giới hạn độ dài/kích thước trước khi cấp phát khi có thể kiểm tra an toàn. Giữ một ngân sách cho bản nguồn, bản sao và kết quả trung gian cùng tồn tại; không chỉ tính kích thước của một mảng.

## 11. Kiểm thử đúng ranh giới sở hữu

Kiểm tra giá trị ngay sau constructor chưa đủ, vì một bản giữ chung tham chiếu cũng có thể cho giá trị đúng lúc đầu. Cần thử sửa dữ liệu ở đúng những đường mà bên gọi được cầm:

1. Tạo đối tượng từ mảng nguồn, sửa nguồn sau đó, xác nhận trạng thái đối tượng không đổi.
2. Lấy mảng từ accessor, sửa kết quả, xác nhận trạng thái nội bộ không đổi.
3. Lấy hai kết quả accessor, sửa một kết quả, xác nhận kết quả kia không bị sửa ngoài hợp đồng.
4. Với phương thức hứa không sửa đầu vào, so sánh dữ liệu đầu vào trước/sau và kiểm tra kết quả đúng.
5. Đưa dữ liệu không hợp lệ vào đường cập nhật, xác nhận trạng thái cũ vẫn hợp lệ khi thao tác thất bại.
6. Với mảng tham chiếu, kiểm tra thêm sửa đối tượng phần tử, không chỉ thay ô trong mảng.
7. Kiểm tra `null`, mảng rỗng, giới hạn độ dài và chỉ số không hợp lệ theo hợp đồng cụ thể.

Đối với `ScoreCard`, mảng rỗng là hợp lệ, `null` bị từ chối, điểm ngoài 0–100 bị từ chối, và độ dài quá 10.000 bị từ chối. Những lựa chọn này là quy tắc của ví dụ, không phải quy tắc tự có của mảng Java.

## 12. Bài tập áp dụng

- Cố ý thay `this.scores = snapshot` thành `this.scores = input` và kiểm tra ca sửa nguồn có phát hiện lỗi không.
- Cố ý thay `return scores.clone()` bằng `return scores` và kiểm tra ca sửa kết quả getter.
- Thiết kế `ScoreCard` tương tự nhưng phần tử là một đối tượng có thể sửa. Xác định những bản sao hiện tại còn để lọt đường thay đổi nào.
- Viết phương thức `reversedCopy(int[] input)` hứa không sửa đầu vào. Chỉ sao chép ở những điểm cần thiết, không clone thêm mảng kết quả mà phương thức không giữ lại.
- Nếu cần cập nhật một lớp có trạng thái thay đổi được, hãy chuẩn bị và kiểm tra dữ liệu mới trước khi thay mảng đang giữ. Thiết kế ca kiểm thử chứng minh thao tác thất bại không để lại trạng thái cập nhật dở dang.

Một thiết kế phòng vệ rõ ràng luôn trả lời được ba câu hỏi: ai còn giữ tham chiếu, ai được phép thay đổi dữ liệu và mức dữ liệu nào thực sự đã được tách biệt.
