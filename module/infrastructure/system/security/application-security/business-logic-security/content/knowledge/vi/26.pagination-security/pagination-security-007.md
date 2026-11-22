# Pagination authorization tests: kiểm thử phân quyền trên mọi trang dữ liệu

Trong chương **Pagination Security**, pagination authorization tests kiểm chứng rằng quyền dữ liệu được giữ ở từng trang, toàn bộ quá trình duyệt và các metadata đi kèm. Trang đầu đúng không chứng minh trang tiếp theo đúng; một cursor hợp lệ cũng không tự cấp quyền đọc mọi bản ghi sau vị trí của nó.

Trong module bảo vệ logic nghiệp vụ, phân trang thường xuất hiện ở danh sách chờ duyệt, lịch sử giao dịch hoặc màn hình chọn đối tượng xử lý hàng loạt. Nếu page, count, cursor hay worker xuất dữ liệu dùng scope khác nhau, người dùng có thể thấy thông tin ngoài quyền hoặc đưa những đối tượng chưa được phép vào một hành động tiếp theo.

Bài học dùng danh sách đề nghị chi có tenant, người tạo và bộ phận. Nội dung mô tả cách thiết kế kiểm thử và mã minh họa trong môi trường được kiểm soát, không phải kết quả chạy test trên một hệ thống cụ thể.

Sau bài này, bạn có thể:

- Xác định invariant về dữ liệu, thứ tự và metadata của một API phân trang.
- Tạo fixture khiến lỗi thiếu scope hoặc lọc quyền sau phân trang dễ xuất hiện.
- Xây oracle độc lập cho từng trang và toàn bộ tập được phép.
- Kiểm thử cursor được chuyển sang actor, tenant hoặc truy vấn khác.
- Kiểm tra cache, quyền thay đổi, dữ liệu biến động và luồng xuất dữ liệu.
- Phân biệt việc được thấy một dòng với quyền thực hiện hành động trên dòng đó.

## 1. Xác định chính xác hợp đồng cần kiểm chứng

Với mỗi request đã xác minh actor và tenant, các invariant cơ bản là:

```text
mọi bản ghi trả về đều thuộc phạm vi được phép đọc
mọi trường trả về đều được phép đọc trên bản ghi đó
count, hasNext và metadata tuân thủ cùng phạm vi
cursor hoặc offset không làm mất các điều kiện quyền
quyền được đánh giá theo ngữ nghĩa hiệu lực đã công bố
request đọc không tự tạo quyết định hay hiệu ứng nghiệp vụ trái phép
```

Cần thêm hợp đồng về tính đầy đủ và thứ tự:

- Có yêu cầu trang đầy kích thước khi còn dữ liệu hợp lệ không?
- Thứ tự có xác định và có khóa phân xử khi các giá trị sort bằng nhau không?
- Count là chính xác, ước tính hay không được trả?
- Có cửa sổ kết quả tối đa hoặc giới hạn tổng lượt đọc không?
- Khi dữ liệu thay đổi giữa hai request, API cam kết snapshot hay chỉ đọc trạng thái từng lần?

Không dùng một oracle đòi snapshot bất biến để đánh giá một API chỉ cam kết đọc dữ liệu hiện hành. Tuy nhiên, dữ liệu thay đổi không phải lý do để trả bản ghi ngoài quyền.

## 2. Tách các thuộc tính kiểm thử

| Thuộc tính | Câu hỏi cần trả lời |
| --- | --- |
| Tính đúng phạm vi | Có bản ghi hoặc trường nào ngoài quyền xuất hiện không? |
| Tính đầy đủ trong hợp đồng | Các bản ghi được phép có bị mất khi duyệt hết tập ổn định không? |
| Tính duy nhất | Có trùng bản ghi ngoài ngữ nghĩa cho phép không? |
| Thứ tự | Kết quả có theo sort và khóa phân xử đã định không? |
| Metadata | Count, cursor và cờ còn trang có cùng biểu diễn tập được phép không? |
| Ràng buộc ngữ cảnh | Token trang có bị dùng để đổi actor, tenant, filter hoặc sort trái hợp đồng không? |
| Hiệu lực quyền | Quyền bị thu hồi hoặc thay đổi giữa các trang được xử lý đúng không? |
| Quyền hành động | Thấy một dòng có bị coi nhầm là được duyệt, sửa hoặc xuất mọi trường không? |

Chỉ kiểm tra “không có ID của tenant B” có thể bỏ sót việc API luôn trả rỗng. Chỉ kiểm tra đủ số lượng có thể bỏ sót việc trả đúng số dòng nhưng sai người sở hữu.

Một bộ test tốt kết hợp nhiều thuộc tính và có ca đối chứng thành công.

## 3. Tạo fixture xen kẽ dữ liệu được phép và bị cấm

Giả sử page size trong test là 3 và có dữ liệu:

| Nhóm | Tenant | Bộ phận | Người tạo | Số bản ghi |
| --- | --- | --- | --- | --- |
| A-own | A | D1 | User A | 7 |
| A-peer | A | D1 | User khác | 3 |
| A-other-dept | A | D2 | Người khác | 4 |
| B | B | Bộ phận tương ứng của B | User B | 5 |

Chính sách ví dụ:

- User A thông thường chỉ đọc 7 đề nghị do mình tạo.
- Reviewer A có phạm vi D1 đọc 10 đề nghị của A-own và A-peer.
- User B đọc dữ liệu được phép trong B.
- User AB có membership ở cả A và B, nhưng mỗi request dùng một scope đã xác minh.
- Chủ thể quản trị xuyên tenant có một hợp đồng và nhóm test riêng.

Đặt timestamp xen kẽ giữa các nhóm thay vì xếp mọi dữ liệu A trước rồi mới tới B. Nếu implementation phân trang toàn cục rồi mới lọc quyền, sự xen kẽ sẽ dễ tạo trang sai hoặc metadata sai.

Tạo một vài timestamp bằng nhau để kiểm tra khóa phân xử. Nếu schema cho phép ID cục bộ trùng giữa tenant, dùng cả trường hợp đó; nếu ID bắt buộc duy nhất toàn cục, giữ đúng schema và thử ID thật của tenant khác.

Dùng chuỗi đánh dấu tổng hợp trong dữ liệu B và trường nội bộ để phát hiện rò rỉ. Chuỗi đó không thay thế oracle về ID, field và count, nhưng hỗ trợ điều tra khi test thất bại.

## 4. Oracle phải độc lập với implementation đang được kiểm tra

Với fixture ổn định, viết tập ID kỳ vọng từ bảng quyền và thứ tự đã định. Không gọi chính hàm `canRead` của production để tính expected nếu đó là phần đang được kiểm chứng.

Ví dụ cho User A:

```text
expectedOrderedIds = [A01, A02, A03, A04, A05, A06, A07]

page 1 = [A01, A02, A03]
page 2 = [A04, A05, A06]
page 3 = [A07]
exact totalCount = 7
```

Thứ tự ID ở đây là nhãn logic của fixture; dữ liệu thời gian và khóa sort cần được tạo để đúng thứ tự đó.

Oracle có thể dùng dữ liệu fixture hoặc một truy vấn kiểm tra riêng được phép đọc dữ liệu tổng hợp trong môi trường test. Không tái sử dụng một repository đang nghi thiếu scope làm nguồn chứng minh rằng không có bản ghi bị lộ.

Với response JSON, kiểm tra trên cây dữ liệu thực tế trước khi chuyển sang một DTO có thể âm thầm bỏ trường lạ. Nếu test chỉ nhìn DTO của SDK, một thuộc tính nhạy cảm bị trả thêm có thể đã bị parser phía test loại bỏ và không còn được quan sát.

## 5. Mỗi ca từ chối cần đối chứng cho route, fixture và quyền

Nhóm đối chứng tối thiểu:

```text
User A + scope A → đọc được danh sách của mình
User B + scope B → đọc được dữ liệu B hợp lệ
User A + scope A + tham số trang hoặc cursor trỏ ngữ cảnh B
  → không được nhận dữ liệu B theo hợp đồng
```

Nếu request B chưa từng thành công với actor B, một lỗi khi actor A dùng nó có thể chỉ do fixture không tồn tại hoặc cursor không hợp lệ về cấu trúc.

Không chỉ dùng token bị sửa làm mất chữ ký. Ca đó thường kiểm chứng xác thực credential; cần token hợp lệ của actor có phạm vi khác để kiểm chứng authorization.

Kết quả phải được xác định từ hợp đồng. Không chấp nhận mọi response lỗi từ `400` đến `599` rồi coi là an toàn. Ví dụ một lỗi server có thể vừa là bug vừa xảy ra sau khi response phụ hoặc tệp xuất đã bị tạo sai.

Ca actor không có bản ghi hợp lệ cần expected rỗng rõ ràng. Nó không thay cho ca actor có dữ liệu được phép, vì một endpoint từ chối mọi người vẫn có thể vượt nhóm test chỉ kiểm tra rỗng.

## 6. Kiểm thử từng trang và toàn bộ chuỗi duyệt

Với fixture không thay đổi và toàn bộ tập nằm trong cửa sổ được hỗ trợ, kiểm tra:

1. Mỗi trang có đúng phạm vi và tập trường cho phép.
2. Page size không vượt hợp đồng.
3. Từng đoạn kết quả khớp thứ tự kỳ vọng nếu API cam kết phân trang trên tập đã lọc quyền.
4. Không có ID trùng trong một lần duyệt ổn định.
5. Duyệt đến cuối trả đủ đúng tập ID kỳ vọng.
6. Cursor không lặp thành vòng và chuỗi kết thúc trong giới hạn test.
7. Count chính xác nếu hợp đồng cung cấp exact count.

Không gọi trang tiếp theo vô hạn khi có lỗi cursor. Đặt trần số trang và phát hiện lặp token để test thất bại có kiểm soát.

Với offset, chạy cả trang đầu, trang giữa, trang cuối, trang hợp lệ không có dữ liệu và ranh giới cửa sổ. Với cursor, bắt đầu từ request không có cursor rồi dùng chính token máy chủ trả, không tự tạo một token giả làm đường thành công.

Nếu endpoint chủ động hỗ trợ các trang không đầy do một cơ chế đã công bố, điều chỉnh oracle theo hợp đồng đó. Vẫn phải chứng minh không mất dữ liệu hợp lệ trong phạm vi cam kết và không tiết lộ vị trí hoặc số lượng ngoài quyền.

## 7. Minh họa Java: duyệt hết một tập ổn định theo oracle độc lập

Ví dụ dùng Java 17. `PageClient` là adapter kiểm thử gọi API thực tế và phân tích JSON theo công cụ của dự án; không dùng một mock trả sẵn đúng dữ liệu để kết luận repository hoặc authorization thực tế an toàn.

Helper giả định API trả các trang đầy trừ trang cuối, sort xác định, dataset ổn định và `totalCount` là chính xác nếu có. Các hệ thống có hợp đồng khác cần oracle tương ứng.

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

record TestContext(String actorFixtureKey, String tenantFixtureKey) {
}

record QuerySpec(int limit, String filterFixtureKey, String sortKey) {
}

record RawPageRow(String id, Set<String> jsonFieldNames) {
}

record PageResult(
        List<RawPageRow> items,
        Long totalCount,
        String nextCursor) {
}

interface PageClient {
    PageResult fetch(TestContext context, QuerySpec query, String cursor)
            throws Exception;
}

final class PaginationAuthorizationChecks {
    private PaginationAuthorizationChecks() {
    }

    static void verifyStableTraversal(
            PageClient client,
            TestContext context,
            QuerySpec query,
            List<String> expectedOrderedIds,
            Set<String> allowedJsonFields,
            int maxPages) throws Exception {
        check(query.limit() > 0 && maxPages > 0, "Invalid test bounds");
        Set<String> expectedSet = new HashSet<>(expectedOrderedIds);
        check(expectedSet.size() == expectedOrderedIds.size(),
                "Fixture oracle contains duplicate IDs");

        List<String> observed = new ArrayList<>();
        Set<String> seenIds = new HashSet<>();
        Set<String> seenCursors = new HashSet<>();
        String cursor = null;

        for (int pageNumber = 0; pageNumber < maxPages; pageNumber++) {
            PageResult page = Objects.requireNonNull(
                    client.fetch(context, query, cursor));
            check(page.items().size() <= query.limit(), "Page size exceeded");
            List<String> pageIds = new ArrayList<>();

            for (RawPageRow row : page.items()) {
                check(expectedSet.contains(row.id()), "Unauthorized ID returned");
                check(seenIds.add(row.id()), "Duplicate ID in stable traversal");
                check(allowedJsonFields.containsAll(row.jsonFieldNames()),
                        "Unexpected JSON field returned");
                pageIds.add(row.id());
            }

            int from = observed.size();
            int to = Math.min(from + query.limit(), expectedOrderedIds.size());
            check(pageIds.equals(expectedOrderedIds.subList(from, to)),
                    "Page does not match the authorized result window");
            observed.addAll(pageIds);

            if (page.totalCount() != null) {
                check(page.totalCount() == (long) expectedOrderedIds.size(),
                        "Count does not match the authorized set");
            }

            if (page.nextCursor() == null) {
                check(observed.equals(expectedOrderedIds),
                        "Traversal ended before the authorized set was complete");
                return;
            }

            check(observed.size() < expectedOrderedIds.size(),
                    "Unexpected next page after the complete fixture set");
            check(!page.nextCursor().isBlank()
                    && seenCursors.add(page.nextCursor()), "Invalid cursor loop");
            cursor = page.nextCursor();
        }
        throw new AssertionError("Traversal exceeded the test page bound");
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

Fixture key giúp test adapter chọn credential và tham số đã tạo, không phải header cho production tin danh tính tự khai. `jsonFieldNames` phải được lấy từ JSON thô; helper này chỉ kiểm tra field cấp dòng, còn cấu trúc lồng nhau cần oracle riêng.

Hàm không dựa vào Java assertions có thể bị tắt. Nó có trần số trang, phát hiện token lặp và kiểm tra cả dữ liệu hợp lệ bị thiếu lẫn dữ liệu ngoài quyền xuất hiện.

## 8. Offset, filter và sort phải cùng giữ scope

Các ca cần tham số hóa theo actor và tenant:

| Biến thể | Điều cần kiểm tra |
| --- | --- |
| Offset đầu, giữa và gần cuối | Không chỉ trang đầu có điều kiện quyền |
| Offset nhảy qua vùng dữ liệu bị cấm trong thứ tự toàn cục | Không trả hoặc tính vị trí dựa trên tập chưa lọc quyền trái hợp đồng |
| Filter OR hoặc nhiều nhánh | Tenant và quyền không bị bỏ ở một nhánh |
| `ownerId` hoặc bộ phận ngoài phạm vi trong filter | Từ chối hoặc giao với phạm vi được phép theo hợp đồng |
| Sort theo thuộc tính nhạy cảm | Không trở thành cách suy luận trường không được phép dùng |
| Tập bộ phận được phép rỗng | Không bỏ điều kiện rồi trả cả tenant |
| Tham số phân trang trùng hoặc mâu thuẫn | Validation và repository không dùng hai giá trị khác nhau |

Với giới hạn result window, phân biệt “không còn dữ liệu” với “không được truy cập sâu hơn qua endpoint này”. Test completeness chỉ áp dụng cho phần mà hợp đồng cam kết có thể duyệt.

Không suy rằng limit nhỏ giúp một query thiếu quyền trở nên an toàn. Một trang chỉ có một dòng vẫn có thể là một dòng hoàn toàn không được đọc.

## 9. Kiểm thử ràng buộc cursor với ngữ cảnh

Một hợp đồng có thể ràng buộc cursor với tenant, actor hoặc fingerprint phạm vi, filter, sort và thời hạn. Khi đó test cần kiểm tra các ràng buộc đã công bố.

| Thao tác với cursor thật do server phát | Kết quả cần giữ |
| --- | --- |
| Dùng tiếp bởi cùng actor và query còn hợp lệ | Có ca thành công thật |
| Đưa cursor A sang tenant B | Không chuyển quyền hoặc dữ liệu của A sang B |
| Đưa cursor của user có phạm vi rộng cho user hẹp | Không dùng phạm vi của người phát ban đầu để vượt quyền |
| User AB chuyển tenant rồi dùng cursor cũ | Không trộn hai scope dù cùng principal |
| Thay filter hoặc sort nhưng giữ cursor | Xử lý theo hợp đồng, không ghép hai tập không tương thích |
| Cursor hết hạn | Không được tự bỏ cursor rồi chạy một query rộng hơn |
| Sửa nội dung token | Không chấp nhận dữ liệu cần bảo vệ tính toàn vẹn đã bị đổi |
| Anchor bị xóa hoặc không còn đọc được | Không fallback lookup toàn cục để mở lại phạm vi |

Nếu hợp đồng quy định cursor không chuyển nhượng giữa actor, cần kỳ vọng lỗi cụ thể khi mismatch. Một API khác có thể cho phép tái sử dụng vị trí nhưng vẫn tái áp dụng đầy đủ quyền hiện tại. Test phải theo đúng lựa chọn đó, không áp một quy tắc lỗi tùy ý cho mọi thiết kế.

Trong mọi trường hợp, cursor không được trở thành capability vượt quyền ngoài hợp đồng. Chữ ký hợp lệ chỉ là một phần bằng chứng, không thay thế kiểm tra actor và dữ liệu hiện tại.

## 10. Count, hasNext và token trang có thể làm lộ dữ liệu

Với fixture User A chỉ đọc được 7 bản ghi, không được trả count của cả tenant hoặc toàn hệ thống nếu caller không có quyền biết con số đó.

Các oracle metadata nên kiểm tra:

- `totalCount` và `totalPages` dựa trên đúng tập được phép theo hợp đồng.
- `hasNext` không phản ánh riêng sự tồn tại của các hàng bị cấm.
- Không có next cursor khi tập hợp lệ đã kết thúc theo hợp đồng của fixture.
- Cursor hoặc error không lộ ID, tenant hay giá trị sort nhạy cảm ngoài phạm vi.
- Các summary, facet và gợi ý liên quan cũng có cùng scope.

Một ca hữu ích là actor không có bản ghi hợp lệ, trong khi tenant khác có nhiều dữ liệu. Response cần đúng ngữ nghĩa rỗng và metadata được phép, không cho thấy một tập ẩn còn rất dài chỉ qua cờ điều hướng.

Nếu API dùng count ước tính hoặc không trả count, không kiểm tra bằng một equality giả định. Thay vào đó kiểm tra hợp đồng tương ứng và phạm vi nguồn số liệu.

Việc cursor trông như chuỗi không đọc được không đủ chứng minh nó không chứa hoặc không sử dụng sai thông tin nhạy cảm. Cần đánh giá cách tạo và cách tiêu thụ nó bằng các ca thực tế.

## 11. Field authorization và quan hệ mở rộng trên từng trang

Một row đúng tenant vẫn có thể chứa trường sai quyền. Ví dụ User A được xem trạng thái và số tiền của đề nghị nhưng không được xem điểm rủi ro hoặc ghi chú điều tra.

Kiểm tra trên mọi trang, không chỉ trang đầu:

```text
các trường bắt buộc của response vẫn đầy đủ
không có field nội bộ ngoài quyền
quan hệ lồng nhau chỉ chứa đối tượng và trường được phép
tham số fields hoặc include không làm rộng quyền
```

Thử trang có bản ghi mang dữ liệu nhạy cảm rõ ràng trong fixture. Nếu field chỉ vắng mặt vì giá trị đang null, test chưa chứng minh cơ chế loại trường hoạt động.

Với dữ liệu con như attachment hoặc ghi chú, cần kiểm tra cả tenant và quan hệ với dòng cha. Một loader dùng cache chỉ theo ID hoặc một truy vấn mở rộng thiếu scope có thể làm trang chính đúng nhưng phần con sai.

Truy vấn sort, filter hoặc aggregate trên trường ẩn cũng cần test theo policy. Không trả trực tiếp một giá trị chưa chắc ngăn được suy luận nếu caller được tự sắp xếp hoặc lọc theo nó.

## 12. Thay đổi quyền giữa hai trang

Helper duyệt ổn định ở trên không dùng để khẳng định kết quả cố định khi quyền thay đổi. Cần một nhóm test riêng với lịch rõ ràng:

```text
User A đọc trang 1
membership, role hoặc phạm vi bộ phận của A thay đổi
đợi tới ranh giới hiệu lực mà hệ thống cam kết
User A gọi trang tiếp theo bằng credential và cursor còn giữ
```

Kết quả phụ thuộc hợp đồng: API có thể từ chối cursor cũ và yêu cầu bắt đầu lại, hoặc tiếp tục trên tập đã áp dụng quyền hiện tại. Nó không được tiếp tục cấp dữ liệu theo quyền cũ ngoài bảo đảm đã công bố.

Kiểm thử cả:

- Mất quyền vào tenant.
- Thu hẹp từ toàn bộ phận xuống chỉ đối tượng sở hữu.
- Mất quyền xem một trường nội bộ.
- Một đối tượng đổi owner hoặc bộ phận.
- Vai trò được cấp lại nhưng phạm vi mới khác trước.

Snapshot dữ liệu không tự đóng băng quyền đọc vĩnh viễn. Nếu sản phẩm có mô hình quyền cho một snapshot hoặc capability riêng, cần nêu rõ hiệu lực và cơ chế thu hồi; không suy từ việc cursor còn chữ ký hợp lệ.

Kỳ vọng phải xét độ trễ cache hoặc token mà hợp đồng cho phép. Không dùng thời gian tạo lệnh phía client làm mốc chứng minh quyền vẫn còn.

## 13. Dữ liệu thay đổi và tính nhất quán của phân trang

Tạo các lịch riêng cho insert, delete và cập nhật trường sort giữa hai request.

| Tình huống | Điều cần xác minh |
| --- | --- |
| Thêm bản ghi ở đầu danh sách | Hành vi trùng hoặc thiếu đúng hợp đồng nhất quán, không làm mất scope |
| Xóa anchor | Không truy cập sai tenant hoặc bỏ mọi điều kiện để tìm vị trí |
| Hai bản ghi cùng timestamp | Thứ tự có khóa phân xử đúng nếu hợp đồng yêu cầu |
| Đổi trạng thái một đề nghị | Filter và metadata phản ánh đúng thời điểm hoặc snapshot đã chọn |
| Đổi bộ phận hoặc owner | Trang tiếp theo vẫn tuân thủ quyền hiệu lực |
| Bản ghi mới đến sau snapshot | Không được tự đưa vào một export hoặc selection snapshot đã cố định ngoài hợp đồng |

Không mặc định mọi bản ghi trùng giữa các trang đều là lỗi authorization. Nó có thể là đặc tính của offset trên dữ liệu thay đổi. Nhưng một bản ghi không có quyền xuất hiện vẫn là lỗi phạm vi, dù có biến động dữ liệu.

Nếu API cam kết snapshot chính xác, test cần tạo đủ thay đổi để chứng minh snapshot đó thực sự được giữ. Một tham số thời gian tạo tối đa có thể không ngăn mọi cập nhật và xóa; đừng dùng nó làm oracle cho một bảo đảm mạnh hơn thực tế.

## 14. Cache, search index và worker xuất dữ liệu

Cache cần được kiểm thử bằng thứ tự làm nóng:

```text
user phạm vi rộng đọc trước
user phạm vi hẹp đọc cùng dạng query sau
tenant A đọc trước rồi tenant B
đảo thứ tự và lặp lại
```

Thử cùng ID cục bộ nếu schema cho phép, cùng filter, cùng page size và các cursor liên quan. Kiểm tra cả response chính, count, projection theo field và cache quan hệ.

Search hoặc bản chiếu báo cáo có thể dùng một đường truy vấn khác với API chi tiết. Đưa các endpoint đó vào cùng ma trận phạm vi thay vì suy rằng repository chính đúng thì toàn bộ danh sách đều đúng.

Với export xử lý nhiều trang, kiểm thử toàn vòng đời:

- Actor hẹp tạo job trong scope A.
- Worker có credential kỹ thuật xử lý job.
- Tệp kết quả chỉ có dữ liệu và trường actor được phép theo policy của job.
- Actor B hoặc scope B không tải được tệp ngoài quyền.
- Thay đổi quyền trong lúc job chờ hoặc trước tải được xử lý đúng hợp đồng.

Một worker có quyền kỹ thuật đọc toàn bảng không nên làm mất scope ban đầu của job. Kiểm tra nội dung tệp bằng oracle fixture, không chỉ tên hoặc metadata của job.

## 15. Dòng được hiển thị không tự cấp quyền thực hiện

Một danh sách chờ xử lý có thể trả các dòng mà actor được xem nhưng không được duyệt. API có thể trả action hint cho giao diện, song endpoint hành động vẫn phải kiểm tra lại.

Những ca cần bổ sung:

- User được đọc nhưng không có permission duyệt gọi trực tiếp endpoint approve.
- User có quyền duyệt nhưng đề nghị do chính họ tạo.
- Đối tượng đổi version hoặc snapshot sau lúc xuất hiện trên trang.
- Client thay danh sách ID của lệnh hàng loạt bằng ID không được phép.
- Client gửi offset–limit thay cho tập đối tượng cụ thể đã xem.

Một trang động không phải bằng chứng đã đồng ý cho mọi đối tượng hiện ở vị trí đó. Lệnh thay đổi cần gắn với ID, version và snapshot phù hợp hoặc một selection snapshot có thẩm quyền.

Khi hành động bị chặn, kiểm tra cả quyết định, ngân sách hoặc reservation, outbox và operation. Không chỉ nhìn response lỗi của endpoint đọc hoặc endpoint hành động.

## 16. Chọn tầng test và kiểm soát môi trường

| Tầng | Bằng chứng có thể thu được | Giới hạn |
| --- | --- | --- |
| Unit policy | Quy tắc actor, scope và field | Chưa chứng minh SQL và middleware thực thi đúng |
| Repository tích hợp | Tenant predicate, join, count và thứ tự | Chưa chứng minh HTTP tạo đúng context |
| API tích hợp | Credential, tenant, query và JSON thực tế | Có thể chưa bao phủ cache hoặc worker ngoài đường chính |
| Cache và nguồn đọc khác | Kết quả qua cache, index hoặc projection | Cần fixture và điều kiện sẵn sàng phù hợp |
| Luồng export hoặc hành động tiếp theo | Scope qua nhiều trang và thành phần | Không tự bao phủ mọi lịch cạnh tranh |

Không chỉ mock repository trả sẵn tập được phép rồi kết luận phân trang thực tế an toàn. Ngược lại, SQL đúng không chứng minh tenant không bị lấy từ một header chưa xác minh.

Giữ fixture độc lập giữa các ca, tránh test duyệt hoặc xóa dữ liệu làm ca đọc sau thay đổi expected. Với index hoặc projection cập nhật trễ, chờ một điều kiện sẵn sàng có giới hạn theo hợp đồng thay vì dùng một khoảng sleep tùy ý.

Các test thời hạn cursor nên kiểm soát được nguồn thời gian ở tầng phù hợp. Chỉnh timestamp client không phải cách kiểm chứng thời hạn có thẩm quyền của server.

## 17. Ma trận hồi quy và cách ghi nhận thất bại

Một nhóm hồi quy nên bao phủ các cặp actor–scope–query và các vị trí trang:

| Ca kiểm thử | Kết quả cần giữ |
| --- | --- |
| Actor own-only duyệt hết fixture ổn định | Đúng 7 ID theo thứ tự và metadata của hợp đồng |
| Reviewer D1 duyệt hết cùng dataset | Đúng tập 10 ID được phép, không có D2 hoặc tenant B |
| User AB dùng hai tenant | Không hợp dữ liệu hoặc tái dùng scope ngầm |
| Cursor của phạm vi rộng được chuyển cho actor hẹp | Không nhận quyền rộng từ token |
| Offset sâu, filter OR và sort khác | Không có đường chỉ bảo vệ trang đầu |
| Count, hasNext và summary | Cùng tập được phép với items |
| Field nhạy cảm có giá trị thật trong fixture | Không xuất hiện ở response thiếu quyền |
| Quyền thay đổi giữa các trang | Đúng ranh giới hiệu lực, không dùng oracle cũ như quyền vĩnh viễn |
| Cache nóng trước bằng scope khác | Không trả nhầm response hoặc projection |
| Duyệt hoặc xuất sau khi đọc trang | Không coi sự xuất hiện trên trang là bằng chứng mọi quyền tiếp theo |

Khi test thất bại, ghi actor fixture, tenant, query, thứ tự trang, ID kỳ vọng và quan sát, count, cursor reference cùng mốc thay đổi quyền hoặc dữ liệu. Không ghi token hoặc credential đầy đủ.

Giữ đủ thông tin để tái hiện nhưng không dump dữ liệu riêng tư ngoài nhu cầu. Với môi trường kiểm thử, dùng marker tổng hợp và định danh fixture thay cho dữ liệu thật.

Có thể dùng các biến thể có chủ đích trong nhánh test để đánh giá độ nhạy, chẳng hạn làm sai count scope hoặc cache key. Nếu một lớp khác vẫn bảo vệ invariant, cần đánh giá đúng tầng thay vì đòi mọi thay đổi riêng lẻ luôn làm một test đầu cuối thất bại.

## 18. Quy trình áp dụng cho một endpoint phân trang

1. Viết rõ chính sách actor, tenant, đối tượng, field và ngữ nghĩa nhất quán của endpoint.
2. Tạo fixture nhiều tenant xen kẽ, đủ nhiều trang và có các giá trị sort bằng nhau.
3. Xác định expected độc lập về ID, thứ tự, trường và metadata cho từng chủ thể.
4. Có ca đối chứng thành công rồi kiểm tra từng trang và toàn chuỗi trong giới hạn hỗ trợ.
5. Thử offset, filter, sort, cursor và các nguồn tham số có thể làm đổi phạm vi.
6. Kiểm tra count, hasNext, quan hệ mở rộng và dữ liệu JSON thực tế.
7. Tách nhóm test quyền thay đổi, dữ liệu biến động, cache và export khỏi oracle dataset ổn định.
8. Kiểm tra riêng quyền hành động sau khi đối tượng được hiển thị.
9. Lưu regression test cùng dữ liệu tái hiện khi thêm nguồn đọc, quan hệ hoặc hợp đồng phân trang mới.

Phân quyền phân trang được kiểm chứng khi mọi trang và thông tin đi kèm đều nằm trong phạm vi của đúng actor ở đúng ngữ cảnh. Oracle độc lập, fixture xen kẽ và các ca thay đổi quyền giúp phát hiện những lỗi mà một trang đầu không có dữ liệu lạ chưa thể chứng minh.
