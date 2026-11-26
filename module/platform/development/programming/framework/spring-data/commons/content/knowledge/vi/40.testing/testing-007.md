# Kiểm thử offset/keyset scrolling với giá trị trùng hoặc null

## 1. Mục tiêu kiểm thử là tính đầy đủ của cả chuỗi window

Trong chương **Kiểm thử** của **SPRING_DATA_COMMONS**, scrolling cần được kiểm tra như một chuỗi truy vấn tiếp nối, không chỉ như một lần lấy vài bản ghi. Các abstraction như Window và ScrollPosition giúp diễn đạt quá trình duyệt, nhưng khả năng hỗ trợ, cách tạo truy vấn và xử lý null vẫn phụ thuộc module cùng store cụ thể.

Một lần gọi trả về đúng ba phần tử chưa chứng minh rằng toàn bộ quá trình:

- Không bỏ sót bản ghi tại ranh giới giữa hai window.
- Không trả lặp lại cùng bản ghi.
- Phân biệt đúng các bản ghi có cùng giá trị sort.
- Xử lý null đúng chính sách đã chọn.
- Dừng đúng khi hết dữ liệu.

Hai rủi ro phổ biến là sort chưa tạo thứ tự toàn phần và cursor không đủ thông tin để xác định điểm tiếp nối.

~~~text
Fixture có chủ đích
  → Window đầu
    → position của phần tử cuối
      → Window tiếp theo
        → ...
          → Đối chiếu toàn bộ ID với kết quả mong đợi độc lập
~~~

Bài này dùng tập dữ liệu tĩnh làm cơ sở trước, sau đó mở rộng sang null và dữ liệu thay đổi giữa các lần gọi.

## 2. Phân biệt offset với keyset

### Offset xác định vị trí theo số phần tử đã đi qua

Offset scrolling tiếp nối bằng vị trí trong tập kết quả đã sắp xếp. Store có thể cần duyệt hoặc bỏ qua phần dữ liệu trước offset; chi phí thực tế phụ thuộc engine, index và kế hoạch thực thi.

Với tập kết quả tĩnh có thứ tự ổn định:

~~~text
[101, 102, 103] [104, 105, 106] [107, 108]
       window 1       window 2    window 3
~~~

Sau window đầu, ứng dụng lấy position của phần tử cuối để bắt đầu window tiếp theo.

### Keyset xác định vị trí theo giá trị khóa sắp xếp

Keyset scrolling dùng các giá trị sort tại vị trí đã đi qua để tạo điều kiện tiếp nối. Với thứ tự score ASC, id ASC, điểm tiếp nối có thể được hiểu bằng cặp:

~~~text
(score = 10, id = 103)
~~~

Nếu các giá trị đều khác null và thứ tự là tăng dần, điều kiện tiếp nối về mặt logic là:

~~~sql
score > 10
or (score = 10 and id > 103)
~~~

Đây là minh họa logic so sánh, không phải SQL mà mọi module bắt buộc phải sinh ra.

Nếu cursor chỉ có score bằng 10, điều kiện score > 10 sẽ làm mất các bản ghi còn lại có score bằng 10. Đổi thành score >= 10 có thể trả lại dữ liệu đã duyệt.

## 3. Giá trị trùng cần khóa phân định duy nhất

Giả sử chỉ sort theo score:

| ID | Score |
| --- | --- |
| 101 | 10 |
| 102 | 10 |
| 103 | 10 |
| 104 | 10 |
| 105 | 20 |

Bốn bản ghi đầu cùng score. Nếu kích thước window là 3, nhóm trùng cắt ngang ranh giới window, rất phù hợp để làm lộ lỗi tiếp nối.

Dùng thứ tự:

~~~text
score ASC, id ASC
~~~

ID duy nhất phân định các phần tử cùng score. Với tập dữ liệu không đổi, mỗi phần tử có một vị trí xác định trong thứ tự này.

Một số module có cơ chế bổ sung khóa định danh cho keyset theo hợp đồng riêng. Khi viết test, nên biết rõ effective sort và có thể khai báo ID tường minh để kỳ vọng dễ đọc. Không lấy hành vi ngầm của một module làm cam kết cho mọi store.

### Offset cũng cần thứ tự ổn định

Offset không tránh được vấn đề trùng sort. Khi database được phép đổi thứ tự các hàng cùng score giữa các truy vấn, offset có thể cắt các nhóm theo cách khác nhau.

Do đó, với cả hai chiến lược, hãy kiểm tra:

1. Có sort tường minh.
2. Sort đủ để phân định duy nhất các kết quả cần duyệt.
3. Các lần tiếp nối giữ nguyên filter, sort và cách diễn giải dữ liệu.
4. Projection trả về đủ dữ liệu để trích xuất position nếu dùng keyset.

## 4. Ngữ nghĩa độc quyền của ScrollPosition

ScrollPosition thể hiện điểm đã đi qua; việc tiếp nối là **exclusive**, nghĩa là không lấy lại phần tử tại điểm đó.

Hai cách khởi đầu offset sau không tương đương:

~~~java
ScrollPosition initial = ScrollPosition.offset();
ScrollPosition afterFirst = ScrollPosition.offset(0L);
~~~

- offset() biểu diễn vị trí khởi đầu, chưa bỏ qua phần tử nào.
- offset(0L) biểu diễn vị trí sau phần tử ở chỉ số 0, nên phần tử đầu tiên không được trả lại.

Với tập ID đã sắp xếp từ 101 đến 108 và window size bằng 3:

| Position đầu vào | Window mong đợi |
| --- | --- |
| offset() | 101, 102, 103 |
| offset(0L) | 102, 103, 104 |

Khi tiếp nối, cách ít phụ thuộc vào tính toán thủ công là:

~~~java
ScrollPosition nextPosition = window.positionAt(window.size() - 1);
~~~

Chỉ gọi positionAt khi window có phần tử. Không lấy position ở chỉ số 0 để tiếp nối cả window, trừ khi chủ đích chỉ muốn bỏ qua phần tử đầu của window đó.

Không tạo lại keyset cursor chỉ từ một property trùng, và không thay position do window cung cấp bằng số trang tự tính.

## 5. Fixture cơ sở: nhóm trùng lớn hơn window

Chọn window size bằng 3 và dữ liệu sau:

| ID | Dataset | Score |
| --- | --- | --- |
| 101 | duplicate-case | 10 |
| 102 | duplicate-case | 10 |
| 103 | duplicate-case | 10 |
| 104 | duplicate-case | 10 |
| 105 | duplicate-case | 20 |
| 106 | duplicate-case | 20 |
| 107 | duplicate-case | 20 |
| 108 | duplicate-case | 30 |

Kỳ vọng độc lập với repository đang kiểm thử:

~~~text
Window 1: [101, 102, 103]
Window 2: [104, 105, 106]
Window 3: [107, 108]

Toàn bộ: [101, 102, 103, 104, 105, 106, 107, 108]
~~~

Fixture này làm lộ:

- Bỏ sót ID 104 nếu keyset chỉ tiếp nối bằng score > 10.
- Lặp ID 101–103 nếu dùng điều kiện chưa loại điểm đã đi qua.
- Lỗi offset lệch một phần tử.
- Lỗi dừng khi kích thước window không bằng kích thước yêu cầu.
- Giả định rằng mọi bản ghi cùng score đều nằm trong một window.

Nên ghi fixture theo thứ tự khác thứ tự truy vấn để test không vô tình dựa vào thứ tự chèn. Oracle vẫn là danh sách ID được xác định từ yêu cầu, không phải kết quả của chính query đang được kiểm tra.

## 6. Repository minh họa và phạm vi store

Các đoạn mã dùng Java 17, JUnit Jupiter, AssertJ và một module hỗ trợ Window cùng ScrollPosition. Ví dụ có thể triển khai bằng repository JPA phù hợp, nhưng không có nghĩa mọi module hoặc mọi dạng query đều hỗ trợ scrolling giống nhau.

Giả sử domain ScrollItem có:

~~~text
id: Long, duy nhất và không null
dataset: String, không null
score: Integer, có thể null
~~~

Với biến thể JPA, domain cần được mapping thành entity, có constructor phù hợp và schema hỗ trợ các trường trên. ID trong fixture được ứng dụng cấp để kỳ vọng kiểm thử dễ xác định; đây không phải yêu cầu chung của scrolling.

~~~java
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;
import org.springframework.data.repository.CrudRepository;

public interface ScrollItemRepository
        extends CrudRepository<ScrollItem, Long> {

    Window<ScrollItem> findFirst3ByDatasetOrderByScoreAscIdAsc(
            String dataset,
            ScrollPosition position);

    Window<ScrollItem> findFirst3ByDatasetAndScoreIsNotNullOrderByScoreAscIdAsc(
            String dataset,
            ScrollPosition position);

    Window<ScrollItem> findFirst3ByDatasetAndScoreIsNullOrderByIdAsc(
            String dataset,
            ScrollPosition position);
}
~~~

Ba phương thức phục vụ ba mục đích:

1. Duyệt tập chung, phù hợp để kiểm tra offset và các dữ liệu không null.
2. Duyệt phần có score khác null bằng thứ tự score, id.
3. Duyệt riêng phần score null nhưng **chỉ sort theo id không null**.

Phương thức thứ ba không yêu cầu cursor mang score null. Score là điều kiện lọc, không phải thành phần sort của truy vấn đó.

Trước khi áp dụng, cần xác nhận module hỗ trợ kiểu phương thức, từ khóa và chiến lược scrolling đã chọn. Việc interface biên dịch không chứng minh implementation thật hỗ trợ toàn bộ khai báo.

## 7. Bộ thu thập window phải có cơ chế dừng

Helper dưới đây dành cho integration test, sử dụng repository thật và domain có getId(). Nó ghi nhận cả ranh giới window lẫn danh sách ID.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;
import org.springframework.data.domain.ScrollPosition;
import org.springframework.data.domain.Window;

record ScrollTrace(
        List<List<Long>> windows,
        List<Long> ids) {
}

static ScrollTrace collectWindows(
        Function<ScrollPosition, Window<ScrollItem>> fetch,
        ScrollPosition initialPosition) {

    List<List<Long>> windows = new ArrayList<>();
    List<Long> ids = new ArrayList<>();
    ScrollPosition position = initialPosition;

    // Giới hạn phù hợp với fixture nhỏ trong bài.
    for (int step = 0; step < 20; step++) {
        Window<ScrollItem> window = fetch.apply(position);

        if (window.isEmpty()) {
            if (window.hasNext()) {
                throw new AssertionError(
                        "Window rỗng nhưng vẫn báo có phần tiếp theo");
            }
            return new ScrollTrace(windows, ids);
        }

        List<Long> currentIds = window.getContent().stream()
                .map(ScrollItem::getId)
                .toList();

        windows.add(currentIds);
        ids.addAll(currentIds);

        if (!window.hasNext()) {
            return new ScrollTrace(windows, ids);
        }

        position = window.positionAt(window.size() - 1);
    }

    throw new AssertionError(
            "Vượt giới hạn window: có thể cursor không tiến triển");
}
~~~

Helper dùng hasNext và positionAt của window, không đoán position từ độ dài danh sách đã thu được.

Giới hạn vòng lặp giúp lỗi cursor không làm bộ test treo vô hạn. Trong fixture lớn hơn, cần chọn giới hạn theo dữ liệu thử nghiệm. Không dùng việc chạm giới hạn như một cách kết thúc thành công.

Khi cần chẩn đoán, nên ghi thêm số lần gọi, position đầu vào và ID đầu/cuối mỗi window. Không chỉ log tổng số phần tử cuối cùng.

## 8. Kiểm thử cùng fixture với cả hai chiến lược

Các đoạn test sau giả định repository được inject là bean thật, fixture đã được ghi và khả kiến đối với truy vấn. Nếu dùng JPA, cần quản lý flush, persistence context và transaction của test phù hợp; không thay repository bằng mock.

### Offset với giá trị trùng

~~~java
@Test
void offsetVisitsEveryDuplicateScoreRowOnce() {
    ScrollTrace trace = collectWindows(
            position ->
                    repository.findFirst3ByDatasetOrderByScoreAscIdAsc(
                            "duplicate-case", position),
            ScrollPosition.offset());

    assertThat(trace.windows()).containsExactly(
            List.of(101L, 102L, 103L),
            List.of(104L, 105L, 106L),
            List.of(107L, 108L));

    assertThat(trace.ids()).containsExactly(
            101L, 102L, 103L, 104L,
            105L, 106L, 107L, 108L);
}
~~~

### Keyset với cùng giá trị trùng

~~~java
@Test
void keysetVisitsEveryDuplicateScoreRowOnce() {
    ScrollTrace trace = collectWindows(
            position ->
                    repository.findFirst3ByDatasetOrderByScoreAscIdAsc(
                            "duplicate-case", position),
            ScrollPosition.keyset());

    assertThat(trace.windows()).containsExactly(
            List.of(101L, 102L, 103L),
            List.of(104L, 105L, 106L),
            List.of(107L, 108L));

    assertThat(trace.ids()).containsExactly(
            101L, 102L, 103L, 104L,
            105L, 106L, 107L, 108L);
}
~~~

Assertion trên toàn bộ danh sách đồng thời kiểm tra thứ tự, số lượng, thiếu và lặp. Chỉ kiểm tra tổng size bằng 8 là chưa đủ: một ID thiếu và một ID lặp vẫn có thể tạo đủ 8 phần tử.

Cả hai test phải được đối chiếu với oracle độc lập. Chỉ so sánh kết quả offset bằng kết quả keyset có thể bỏ qua trường hợp hai implementation cùng sai.

### Kiểm thử vị trí ban đầu

~~~java
@Test
void explicitOffsetZeroSkipsTheFirstRow() {
    Window<ScrollItem> initial =
            repository.findFirst3ByDatasetOrderByScoreAscIdAsc(
                    "duplicate-case", ScrollPosition.offset());

    Window<ScrollItem> afterIndexZero =
            repository.findFirst3ByDatasetOrderByScoreAscIdAsc(
                    "duplicate-case", ScrollPosition.offset(0L));

    assertThat(initial.getContent())
            .extracting(ScrollItem::getId)
            .containsExactly(101L, 102L, 103L);

    assertThat(afterIndexZero.getContent())
            .extracting(ScrollItem::getId)
            .containsExactly(102L, 103L, 104L);
}
~~~

Test này tách riêng một lỗi off-by-one thường bị che bởi vòng lặp nhiều window.

## 9. Null tạo ra hai vấn đề khác nhau

### Thứ tự đặt null

Với score ASC, vị trí null phụ thuộc query, store và cấu hình. Không giả định mọi database hoặc document store đều đưa null về cùng đầu hoặc cuối.

Các yêu cầu như nullsFirst hoặc nullsLast trong API sắp xếp có thể là gợi ý mà module/store không hỗ trợ hoặc không áp dụng như mong muốn. Nếu thứ tự null là hợp đồng của sản phẩm, phải thực thi và kiểm tra nó trên môi trường thực tế.

### Điều kiện tiếp nối bằng keyset

Keyset filtering cần các khóa sort có giá trị phù hợp để so sánh và trích xuất cursor. Không nên mặc định một sort property nullable có thể được tiếp nối an toàn như một giá trị thông thường.

Trong SQL, chẳng hạn:

~~~sql
score > null
score = null
~~~

không tương đương với so sánh một giá trị cụ thể. Vì vậy, viết thêm ID vào sort chưa tự giải quyết phần so sánh score null.

Module có thể từ chối, không trích xuất được keyset hoặc cho kết quả không như kỳ vọng tùy cơ chế đang dùng. Không đặt một assertion chung rằng mọi store phải ném cùng loại exception ở cùng thời điểm.

**Với keyset, chính sách an toàn cần bảo đảm các giá trị dùng làm khóa sort trong tập đang duyệt không null, hoặc sử dụng một cơ chế xử lý null được module hỗ trợ rõ ràng.**

## 10. Kiểm thử offset trên fixture có null

Bổ sung hai hàng:

| ID | Dataset | Score |
| --- | --- | --- |
| 109 | duplicate-case | null |
| 110 | duplicate-case | null |

Với offset, có thể kiểm tra tính đầy đủ mà chưa áp đặt thứ tự null giữa các store:

~~~java
@Test
void offsetDoesNotLoseRowsWhenScoresContainNull() {
    ScrollTrace trace = collectWindows(
            position ->
                    repository.findFirst3ByDatasetOrderByScoreAscIdAsc(
                            "duplicate-case", position),
            ScrollPosition.offset());

    assertThat(trace.ids()).containsExactlyInAnyOrder(
            101L, 102L, 103L, 104L, 105L,
            106L, 107L, 108L, 109L, 110L);
}
~~~

Assertion này chứng minh đúng tập ID và đúng số lần xuất hiện trong fixture tĩnh. Nó **chưa chứng minh chính sách null-first hoặc null-last**.

Nếu ứng dụng quy định null-last, cần có query hoặc kế hoạch duyệt thực sự thực hiện chính sách đó rồi bổ sung assertion thứ tự chính xác. Không sửa oracle theo thứ tự database tình cờ trả về và coi đó là hợp đồng sản phẩm.

ID vẫn phải phân định thứ tự trong nhóm cùng score, bao gồm nhóm null nếu store áp dụng thứ tự đó. Nên có nhiều hơn một hàng null để tránh bỏ qua việc xử lý một nhóm đồng hạng.

## 11. Chính sách keyset với null: chia hai pha

Một lựa chọn ở tầng ứng dụng là:

~~~text
Pha 1: score IS NOT NULL, sort score ASC, id ASC.
Pha 2: score IS NULL, sort id ASC.
Kết quả toàn bộ: pha 1 rồi pha 2.
~~~

Chính sách này diễn đạt null-last bằng thứ tự các pha. Trong pha 2, cursor chỉ cần khóa id không null; không dùng score null làm thành phần keyset.

Đây là một thiết kế điều phối của ứng dụng, không phải khả năng mà Window tự động bổ sung.

~~~java
@Test
void keysetCanVisitNullRowsThroughAnIdSortedSecondPhase() {
    ScrollTrace nonNullPart = collectWindows(
            position ->
                    repository
                            .findFirst3ByDatasetAndScoreIsNotNullOrderByScoreAscIdAsc(
                                    "duplicate-case", position),
            ScrollPosition.keyset());

    ScrollTrace nullPart = collectWindows(
            position ->
                    repository.findFirst3ByDatasetAndScoreIsNullOrderByIdAsc(
                            "duplicate-case", position),
            ScrollPosition.keyset());

    List<Long> combined = new ArrayList<>(nonNullPart.ids());
    combined.addAll(nullPart.ids());

    assertThat(combined).containsExactly(
            101L, 102L, 103L, 104L, 105L,
            106L, 107L, 108L, 109L, 110L);
}
~~~

Cần bổ sung các ca:

- Không có hàng null: pha 2 rỗng.
- Toàn bộ score đều null: pha 1 rỗng, pha 2 vẫn duyệt đủ.
- Số hàng null lớn hơn window size.
- Nhóm null có đúng số phần tử bằng kích thước window.
- Tiếp nối ngay tại điểm chuyển pha.

Nếu API trả cursor cho client, cursor cấp ứng dụng cần ghi nhận **đang ở pha nào**, cùng position và ngữ cảnh truy vấn tương ứng. Cursor của pha 1 không được đưa trực tiếp vào query của pha 2.

Khi muốn so sánh offset với keyset trên cùng chính sách null-last, có thể áp dụng cùng hai pha cho cả hai chiến lược. Không so sánh thứ tự hai pha với một query offset đang dùng quy tắc null mặc định khác rồi kết luận keyset sai.

### Một lựa chọn khác: khóa sort chuẩn hóa không null

Có thể thiết kế các trường sort ổn định như:

~~~text
scoreGroup: 0 cho score có giá trị, 1 cho score null.
sortScore: giá trị score thật, hoặc giá trị quy ước khi score null.
id: khóa phân định duy nhất.

Sort: scoreGroup ASC, sortScore ASC, id ASC.
~~~

Mọi thành phần keyset phải có giá trị không null và mapping phù hợp. Cần bảo đảm trường chuẩn hóa nhất quán khi ghi/cập nhật dữ liệu.

Không chỉ thay null bằng một sentinel rồi bỏ qua khả năng sentinel trùng giá trị nghiệp vụ. Thành phần phân nhóm giúp giữ được khác biệt giữa “không có score” và một score thật bằng giá trị quy ước.

Nếu chuẩn hóa bằng biểu thức truy vấn hoặc projection, còn phải kiểm tra module hỗ trợ scrolling và trích xuất keyset cho dạng kết quả đó. Không mặc định mọi query tùy biến đều hỗ trợ.

## 12. Projection phải đủ dữ liệu để tạo position

Với keyset sort theo score và id, kết quả cần cung cấp các giá trị mà hạ tầng yêu cầu để trích xuất position.

Một projection chỉ có label có thể đọc được dữ liệu nhưng không đủ cho quá trình tiếp nối theo sort key. Cách lỗi xuất hiện phụ thuộc module và kiểu projection.

Test nên thực hiện cả:

~~~text
Gọi query → Đọc nội dung window → Lấy positionAt → Gọi window tiếp theo.
~~~

Nếu test chỉ xác nhận window đầu có dữ liệu, nó có thể bỏ qua lỗi xuất hiện khi trích xuất hoặc sử dụng position.

Cần giữ thống nhất kiểu dữ liệu của sort key. Việc tự mã hóa cursor thành chuỗi rồi làm mất độ chính xác timestamp, số thập phân hoặc kiểu ID có thể tạo lỗi ranh giới ngay cả khi query ban đầu đúng.

## 13. Ma trận ca kiểm thử tối thiểu

Với kích thước window là 3:

| Dữ liệu | Điều cần xác nhận |
| --- | --- |
| 0 phần tử | Window rỗng, không cố lấy position của phần tử cuối |
| 1 hoặc 2 phần tử | Window cuối chưa đầy vẫn được thu thập |
| Đúng 3 phần tử | Không bỏ window hoặc dựa vào một lần gọi rỗng không cần thiết |
| 4 phần tử | Tiếp nối đúng sau window đầu |
| 6 phần tử | Trường hợp số lượng chia hết cho kích thước window |
| 7 hoặc 8 phần tử | Dừng đúng sau phần dư |
| Mọi score giống nhau | ID phân định toàn bộ chuỗi |
| Nhóm trùng vượt ranh giới | Không bỏ hoặc lặp phần còn lại của nhóm |
| Một hoặc nhiều score null | Tuân thủ chính sách null đã công bố |
| Toàn bộ score null | Chính sách loại bỏ hoặc pha riêng hoạt động đúng |
| Sort giảm dần | Điều kiện tiếp nối đúng chiều, không tái dùng giả định ASC |
| Projection có sort key | Trích xuất và sử dụng position thành công |

Không dùng mọi assertion của sort tăng dần cho sort giảm dần. Ví dụ, điều kiện tiếp nối có thể đổi chiều so sánh; với sort hỗn hợp, từng thành phần cần được diễn giải theo hướng tương ứng.

Nếu module hỗ trợ duyệt ngược, hãy kiểm thử riêng hợp đồng duyệt ngược. Không suy ra việc đảo danh sách trên client tương đương với keyset backward.

## 14. Tách bài toán dữ liệu tĩnh và dữ liệu thay đổi

Các test cơ sở ở trên giả định tập kết quả không đổi giữa các lần gọi. Khi dữ liệu thay đổi, offset và keyset có hành vi khác nhau và không tự cung cấp snapshot chung cho toàn bộ phiên duyệt.

### Chèn trước vị trí đã đi qua

Đã đọc 101, 102, 103; sau đó có một hàng mới đứng trước chúng trong thứ tự.

- Offset có thể bị dịch vị trí và trả lại một hàng đã đọc.
- Keyset tiếp nối sau cặp khóa của 103 nên tránh được kiểu dịch offset đó khi khóa sort của các hàng liên quan không đổi.
- Hàng mới nằm trước cursor có thể không xuất hiện trong phần còn lại của phiên keyset.

### Xóa trước vị trí đã đi qua

Đã đọc 101, 102, 103; sau đó 101 bị xóa và thay đổi được nhìn thấy ở truy vấn tiếp theo.

- Offset có thể bỏ qua một hàng chưa đọc do các vị trí dồn lên.
- Keyset dựa trên giá trị khóa tiếp nối không bị dịch theo số lượng hàng đã xóa theo cùng cách.

### Cập nhật khóa sort hoặc trạng thái null

Nếu score của một hàng thay đổi, hàng có thể chuyển từ trước cursor sang sau cursor hoặc ngược lại. Với thiết kế hai pha, chuyển score giữa null và khác null còn có thể làm hàng chuyển pha.

Keyset không tự bảo đảm không thiếu hoặc không lặp trong mọi tình huống này. Nếu sản phẩm cần một ảnh chụp nhất quán, phải thiết kế snapshot, phiên dữ liệu, khóa sort bất biến hoặc cơ chế khác phù hợp với store.

Test thay đổi đồng thời cần xác định rõ:

- Thao tác thay đổi đã commit khi nào.
- Truy vấn tiếp theo có nhìn thấy commit đó không.
- Isolation và transaction của test có che thay đổi hay không.
- Hợp đồng sản phẩm là duyệt snapshot hay duyệt dữ liệu đang thay đổi.

Không đặt kỳ vọng trái với hợp đồng đã chọn rồi xem mọi khác biệt là lỗi của scrolling.

## 15. Môi trường và chẩn đoán lỗi

Mock repository chỉ trả Window được dựng sẵn; nó không xác minh query tiếp nối, cách xử lý null hoặc trích xuất keyset thật. Nên chạy những ca trọng tâm trên repository thật cùng store có cấu hình phù hợp.

Nếu production phụ thuộc collation, kiểu dữ liệu hoặc null ordering cụ thể, môi trường test cần đủ tương đồng để phát hiện khác biệt đó.

| Biểu hiện | Nguyên nhân cần kiểm tra |
| --- | --- |
| Thiếu phần còn lại của nhóm score trùng | Cursor thiếu khóa phân định hoặc điều kiện tiếp nối sai |
| Phần tử đầu tiên luôn bị bỏ | Dùng offset(0L) thay vị trí initial |
| Lặp đầu window tiếp theo | Tái sử dụng sai position hoặc so sánh không exclusive |
| Chỉ lỗi khi lấy positionAt | Thiếu sort key trong projection hoặc không trích xuất được giá trị |
| Chỉ lỗi khi xuất hiện null | Khóa keyset nullable hoặc chính sách null chưa được thực thi |
| Tổng số đúng nhưng có ID sai | Assertion chỉ đếm mà không đối chiếu danh tính |
| Test lúc xanh lúc đỏ | Thiếu thứ tự toàn phần, dữ liệu dùng chung hoặc thay đổi đồng thời |
| Vòng lặp không kết thúc | Cursor không tiến triển hoặc helper bỏ qua tín hiệu kết thúc |

Fixture cần được cô lập, có phạm vi dataset rõ ràng và được dọn theo cơ chế phù hợp của store. Với ID cố định như ví dụ, không chạy các test ghi cùng ID vào chung database theo cách gây xung đột.

Không khái quát rollback của một test JPA thành cơ chế dọn dữ liệu cho mọi document, graph hoặc reactive store.

## 16. Bài tập áp dụng

1. Dựng fixture nhóm score bằng 10 có ít nhất bốn hàng và window size bằng 3.
2. Chạy offset và keyset, đối chiếu từng window cùng toàn bộ ID với oracle độc lập.
3. Phân biệt offset() với offset(0L) bằng một test riêng.
4. Bổ sung nhiều hàng null và chọn chính sách: loại khỏi tập duyệt, chia pha hoặc chuẩn hóa khóa.
5. Kiểm tra chính sách đó với trường hợp mọi score đều null.
6. Nếu dùng projection, tiếp nối qua ít nhất hai window thay vì chỉ đọc window đầu.
7. Mô phỏng một lần chèn, xóa hoặc đổi score giữa hai lần đọc và mô tả hành vi theo hợp đồng nhất quán đã chọn.

Một bộ test scrolling có giá trị phải chứng minh cả đường đi qua ranh giới window. Giá trị trùng đòi hỏi khóa phân định; null đòi hỏi chính sách rõ ràng; dữ liệu thay đổi đòi hỏi hợp đồng nhất quán phù hợp với store.
