# Kiểu con loại trừ nhau hoặc có thể chồng lấp

Khi chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu, một thực thể tổng quát (*supertype*, hay kiểu cha) có thể được chuyên biệt hóa thành nhiều kiểu con (*subtype*). Câu hỏi quyết định không chỉ là “có những kiểu con nào?”, mà còn là: **cùng một thực thể có được thuộc nhiều kiểu con trong cùng một thời điểm và cùng phạm vi nghiệp vụ hay không?**

Trong chương **Kế thừa và phân cấp** của chủ đề mô hình hóa dữ liệu, câu trả lời tạo ra hai quy tắc rất khác nhau:

- **Loại trừ nhau (disjoint specialization):** mỗi thực thể thuộc **tối đa một** kiểu con trong nhóm đang xét.
- **Có thể chồng lấp (overlapping specialization):** một thực thể được phép thuộc **nhiều** kiểu con trong nhóm đang xét.

Đây là ràng buộc nghiệp vụ cần được thể hiện trong mô hình khái niệm, chuyển đúng sang lược đồ logic và, khi cần, được cơ sở dữ liệu kiểm soát. Chọn sai sẽ dẫn đến dữ liệu không hợp lệ, cột thừa, truy vấn khó hiểu hoặc thiết kế khó tiến hóa.

## 1. Hiểu quy tắc qua hai ví dụ

### Ví dụ A: Một lần thực hiện đơn hàng chỉ có một phương thức

Giả sử hệ thống quy định **mỗi lần thực hiện đơn hàng** (*fulfillment*) chỉ theo một phương thức:

- **Giao tận nơi (Delivery):** cần địa chỉ nhận hàng.
- **Nhận tại điểm lấy hàng (Pickup):** cần địa điểm nhận.

Một bản ghi fulfillment không thể đồng thời là Delivery và Pickup. Đây là **kiểu con loại trừ nhau**.

Lưu ý đơn hàng có thể được chia thành nhiều lần thực hiện riêng biệt. Khi đó, một đơn hàng có thể có cả lần giao hàng và lần nhận tại cửa hàng; **quy tắc loại trừ vẫn đúng ở cấp mỗi fulfillment**. Việc chọn đúng thực thể và phạm vi là điều kiện để phát biểu ràng buộc chính xác.

### Ví dụ B: Một người dùng có thể vừa mua vừa bán

Một nền tảng thương mại cho phép người dùng có các vai trò:

- **Người mua (Buyer):** có thông tin phục vụ chương trình khách hàng thân thiết.
- **Người bán (Seller):** có hồ sơ cửa hàng.

Cùng một người dùng có thể là Buyer, Seller, cả hai hoặc chưa tham gia vai trò nào. Đây là **kiểu con có thể chồng lấp**. Nếu ép người dùng chọn duy nhất một loại, hệ thống sẽ phải tạo tài khoản trùng lặp hoặc từ chối một trạng thái nghiệp vụ hợp lệ.

| Thực thể | Thuộc kiểu con A | Thuộc kiểu con B | Hợp lệ khi loại trừ? | Hợp lệ khi chồng lấp? |
| --- | --- | --- | --- | --- |
| X | Có | Không | Có | Có |
| Y | Không | Có | Có | Có |
| Z | Có | Có | **Không** | Có |
| W | Không | Không | Tùy quy tắc bao phủ | Tùy quy tắc bao phủ |

Hàng W cho thấy còn một câu hỏi độc lập: có bắt buộc thực thể phải thuộc ít nhất một kiểu con hay không?

## 2. Định nghĩa chính xác bằng tập hợp

Gọi \\(S\\) là tập các thực thể của kiểu cha; \\(A, B\\) là tập thực thể của hai kiểu con, với \\(A \\subseteq S\\) và \\(B \\subseteq S\\).

**Loại trừ nhau:** \\(A \\cap B = \\varnothing\\). Với nhiều kiểu con, điều kiện áp dụng cho **mọi cặp kiểu con** trong nhóm loại trừ nhau.

**Có thể chồng lấp:** không áp đặt điều kiện giao bằng rỗng; \\(A \\cap B\\) **được phép khác rỗng**. Quy tắc này không yêu cầu phải tồn tại thực thể thuộc cả hai: hai tập vẫn có thể tình cờ chưa giao nhau trong dữ liệu hiện tại.

Nếu một thực thể có các thuộc tính chung và các thuộc tính riêng cho từng kiểu con, nên giữ **một định danh chung** ở kiểu cha. Chẳng hạn, Buyer và Seller của cùng một người dùng đều mang cùng \\(user\_id\\), không phải hai người dùng độc lập.

### Loại trừ/chồng lấp khác với toàn phần/bộ phận

**Disjoint/overlapping** trả lời “tối đa bao nhiêu kiểu con?”, còn **total/partial specialization** trả lời “tối thiểu bao nhiêu kiểu con?”.

| Quy tắc kết hợp | Số kiểu con của một thực thể | Ví dụ |
| --- | --- | --- |
| Loại trừ + toàn phần | **Đúng 1** | Fulfillment đã xác lập bắt buộc là Delivery hoặc Pickup |
| Loại trừ + bộ phận | **0 hoặc 1** | Fulfillment mới tạo có thể chưa chọn phương thức |
| Chồng lấp + toàn phần | **Ít nhất 1** | Tài khoản đã kích hoạt phải là Buyer, Seller hoặc cả hai |
| Chồng lấp + bộ phận | **0, 1 hoặc nhiều** | Người dùng mới đăng ký có thể chưa mua và chưa bán |

Trong ký pháp EER (*Enhanced Entity–Relationship*), ràng buộc loại trừ thường được ký hiệu **d**, chồng lấp là **o**; tính toàn phần/bộ phận thường dùng đường đôi/đường đơn nối kiểu cha với nút chuyên biệt hóa. Ký pháp cụ thể tùy công cụ, nhưng **hai trục ràng buộc phải được xác định riêng**.

## 3. Xác định đúng quy tắc từ yêu cầu nghiệp vụ

Hãy hỏi người hiểu nghiệp vụ những câu sau trước khi chọn thiết kế bảng:

1. **Định danh nào đang được phân loại?** Một tài khoản, một giao dịch, một sản phẩm hay một lần thực hiện đơn hàng? Không trộn quy tắc ở cấp đơn hàng với quy tắc ở cấp từng lần thực hiện.
2. **Tại cùng một thời điểm, A và B có thể cùng đúng không?** Nếu có, nhóm kiểu con không loại trừ nhau. Nếu chỉ “chưa từng thấy” trường hợp đó, chưa đủ cơ sở kết luận loại trừ.
3. **Một thực thể có thể không thuộc kiểu con nào không?** Câu này xác định toàn phần hay bộ phận.
4. **Vai trò có đổi theo thời gian hoặc theo ngữ cảnh không?** Một nhân viên có thể là người quản lý trong một dự án và người đóng góp trong dự án khác. Phân loại có thể phụ thuộc dự án, thời hạn hiệu lực hoặc hợp đồng.
5. **Các kiểu con có dữ liệu và hành vi riêng thực sự không?** Nếu chỉ là nhãn quyền hạn, một bảng quan hệ vai trò có thể hợp lý hơn cấu trúc kế thừa nhiều tầng.

Một phát biểu nghiệp vụ có thể kiểm chứng nên có dạng:

> “Với mỗi fulfillment, tại một thời điểm, đúng một phương thức DELIVERY hoặc PICKUP được áp dụng; địa chỉ giao hàng chỉ tồn tại với DELIVERY và điểm nhận chỉ tồn tại với PICKUP.”

Hoặc:

> “Một user có thể có đồng thời hồ sơ buyer và hồ sơ seller; mỗi loại hồ sơ xuất hiện nhiều nhất một lần cho mỗi user.”

Hai phát biểu này đủ cụ thể để chuyển thành khóa, ràng buộc và kiểm thử.

## 4. Hiện thực loại trừ nhau trong cơ sở dữ liệu quan hệ

### 4.1. Một bảng cho cả phân cấp (single-table inheritance)

Khi tập kiểu con khá ổn định và mỗi thực thể có **đúng một** loại, có thể dùng một bảng với cột phân biệt kiểu (*discriminator*):

~~~sql
-- PostgreSQL
CREATE TABLE fulfillments (
    fulfillment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id       BIGINT NOT NULL,
    method         TEXT NOT NULL
                   CHECK (method IN ('DELIVERY', 'PICKUP')),
    delivery_address TEXT,
    pickup_location  TEXT,

    CONSTRAINT valid_fulfillment_details CHECK (
        (method = 'DELIVERY'
            AND delivery_address IS NOT NULL
            AND pickup_location IS NULL)
        OR
        (method = 'PICKUP'
            AND pickup_location IS NOT NULL
            AND delivery_address IS NULL)
    )
);
~~~

Ở đây:

- \\(fulfillment\_id\\) định danh một lần thực hiện; \\(order\_id\\) liên kết về đơn hàng (trong hệ thống hoàn chỉnh nên có khóa ngoại tới bảng đơn hàng).
- \\(method\\) **NOT NULL** và chỉ nhận hai giá trị, nên mô hình thể hiện **toàn phần**.
- Ràng buộc \\(CHECK\\) buộc các thuộc tính riêng phù hợp với đúng một loại, ngăn trường hợp nhập cả địa chỉ giao và địa điểm nhận cho cùng một fulfillment.
- Ràng buộc chỉ làm rõ sự thật nghiệp vụ; ứng dụng vẫn cần thông báo lỗi thân thiện khi ghi dữ liệu không hợp lệ.

Ví dụ:

~~~sql
INSERT INTO fulfillments (order_id, method, delivery_address)
VALUES (901, 'DELIVERY', '12 Nguyen Hue, Quan 1');

-- Bị từ chối: một fulfillment không thể mang cả hai loại thông tin.
INSERT INTO fulfillments (
    order_id, method, delivery_address, pickup_location
)
VALUES (902, 'PICKUP', '12 Nguyen Hue, Quan 1', 'Cua hang A');
~~~

Thiết kế này đơn giản để truy vấn và bảo đảm loại trừ. Đổi lại, khi số kiểu con nhiều và mỗi loại có nhiều thuộc tính riêng, bảng sẽ chứa nhiều cột nullable; mỗi lần thêm loại mới có thể phải thay đổi \\(CHECK\\), cột và mã ứng dụng.

### 4.2. Một bảng cha, mỗi kiểu con một bảng (class-table inheritance)

Cũng có thể đặt thuộc tính chung trong \\(fulfillments\\), thông tin giao hàng trong \\(delivery\_details\\) và thông tin nhận tại điểm trong \\(pickup\_details\\). Khóa chính của từng bảng con đồng thời là khóa ngoại tới bảng cha.

Tuy nhiên, **chỉ có hai khóa ngoại trỏ về bảng cha chưa đủ bảo đảm loại trừ**: cùng một \\(fulfillment\_id\\) vẫn có thể xuất hiện ở cả hai bảng con. Những phương án kiểm soát gồm:

- Giữ \\(method\\) ở bảng cha; trong bảng con dùng discriminator cố định và **khóa ngoại ghép** tới cặp \\((fulfillment\_id, method)\\) duy nhất ở bảng cha, để loại bản ghi con phải khớp với loại cha.
- Hoặc áp dụng trigger/ràng buộc giao dịch kiểm soát tính loại trừ giữa các bảng. Trigger phải xử lý đúng các thao tác đồng thời, không chỉ truy vấn kiểm tra sơ bộ.

Ngay cả khi đã loại trừ được hai bảng con, yêu cầu **“mỗi cha phải có đúng một con”** còn cần kiểm soát tính bao phủ. Khóa ngoại từ bảng con lên bảng cha chỉ bảo đảm “con có cha”; nó không bảo đảm “cha có con”. Với nhiều bảng con, yêu cầu toàn phần thường cần quy trình ghi trong cùng giao dịch kèm cơ chế kiểm tra phù hợp, hoặc một thiết kế một bảng như ví dụ trên.

## 5. Hiện thực kiểu con chồng lấp trong cơ sở dữ liệu quan hệ

### 5.1. Hồ sơ con độc lập, dùng chung khóa cha

Với trường hợp người dùng có thể vừa mua vừa bán, một discriminator chỉ nhận một giá trị là **không đủ biểu diễn**. Thiết kế dưới đây cho phép mỗi tài khoản có từng loại hồ sơ:

~~~sql
-- PostgreSQL
CREATE TABLE app_users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email   TEXT NOT NULL UNIQUE
);

CREATE TABLE buyer_profiles (
    user_id        BIGINT PRIMARY KEY
                   REFERENCES app_users(user_id) ON DELETE CASCADE,
    loyalty_points INTEGER NOT NULL DEFAULT 0
                   CHECK (loyalty_points >= 0)
);

CREATE TABLE seller_profiles (
    user_id   BIGINT PRIMARY KEY
              REFERENCES app_users(user_id) ON DELETE CASCADE,
    shop_name TEXT NOT NULL
);
~~~

Mỗi bảng con có khóa chính là \\(user\_id\\), vì vậy **mỗi người dùng có tối đa một buyer profile và một seller profile**. Hai khóa ngoại độc lập cho phép cùng một \\(user\_id\\) xuất hiện ở cả hai bảng; đây chính là ý nghĩa của chồng lấp.

~~~sql
INSERT INTO app_users (email)
VALUES ('minh@example.test')
RETURNING user_id;

-- Giả sử lệnh trên trả về user_id = 1.
INSERT INTO buyer_profiles (user_id, loyalty_points)
VALUES (1, 120);

INSERT INTO seller_profiles (user_id, shop_name)
VALUES (1, 'Minh Store');

-- Người dùng có đồng thời cả hai kiểu con.
SELECT u.user_id, u.email, b.loyalty_points, s.shop_name
FROM app_users AS u
JOIN buyer_profiles  AS b ON b.user_id = u.user_id
JOIN seller_profiles AS s ON s.user_id = u.user_id;
~~~

Kết quả truy vấn gồm những người dùng vừa có hồ sơ Buyer vừa có hồ sơ Seller. Còn để lấy tất cả người dùng cùng vai trò (kể cả người không có vai trò nào), dùng \\(LEFT JOIN\\) từ \\(app\_users\\) sang các bảng con.

Ví dụ đang là **chồng lấp + bộ phận**: người dùng có thể chưa có cả hai hồ sơ. Nếu nghiệp vụ đòi **chồng lấp + toàn phần**, cần thêm kiểm tra để mọi người dùng đủ điều kiện có ít nhất một hồ sơ; chỉ dùng các khóa ngoại ở trên sẽ không đáp ứng được.

### 5.2. Nếu vai trò chỉ là nhãn, dùng bảng quan hệ

Không phải vai trò nào cũng cần một bảng kiểu con. Nếu Buyer và Seller chỉ là phân loại hoặc quyền, chưa có thuộc tính riêng, mô hình quan hệ nhiều-nhiều gọn hơn:

~~~sql
CREATE TABLE user_roles (
    user_id   BIGINT NOT NULL
              REFERENCES app_users(user_id) ON DELETE CASCADE,
    role_code TEXT NOT NULL
              CHECK (role_code IN ('BUYER', 'SELLER')),
    PRIMARY KEY (user_id, role_code)
);

-- Một người dùng có cả hai vai trò là hợp lệ.
INSERT INTO user_roles (user_id, role_code)
VALUES (1, 'BUYER'), (1, 'SELLER');
~~~

Khóa chính ghép loại bản ghi vai trò trùng, nhưng **không cấm nhiều vai trò khác nhau cho cùng một người dùng**. Khi một vai trò có dữ liệu riêng, có thể bổ sung bảng hồ sơ theo vai trò. Nếu kết hợp \\(user\_roles\\) và các bảng hồ sơ, phải quyết định **nguồn dữ liệu chuẩn** của tư cách thành viên để tránh tình huống có role nhưng không có profile, hoặc ngược lại.

Không nên tạo hai cột \\(is\_buyer\\), \\(is\_seller\\) và một tập bảng con độc lập rồi cập nhật riêng rẽ nếu không có ràng buộc giữ chúng đồng bộ.

## 6. Chọn cách ánh xạ phân cấp xuống bảng

| Cách ánh xạ | Phù hợp với | Ưu điểm | Điểm cần lưu ý |
| --- | --- | --- | --- |
| **Một bảng toàn bộ phân cấp** (*single table*) | Ít loại, đặc biệt là loại trừ nhau | Truy vấn đơn giản, dễ đặt \\(CHECK\\) cho một hàng | Nhiều cột nullable; thêm loại có thể đổi cấu trúc bảng |
| **Bảng cha + bảng con** (*class table*) | Kiểu con có thuộc tính riêng, nhất là kiểu chồng lấp | Tái sử dụng định danh cha, chuẩn hóa thuộc tính riêng, thể hiện đồng thời nhiều vai trò | Cần JOIN; nếu loại trừ hoặc toàn phần phải có ràng buộc bổ sung |
| **Mỗi kiểu cụ thể một bảng** (*concrete table*) | Các loại tương đối độc lập, ít truy vấn trên kiểu cha | Mỗi bảng chứa đúng thuộc tính của loại | Dễ lặp cột chung; khó tạo khóa ngoại chung và truy vấn toàn bộ kiểu cha |
| **Bảng quan hệ thành viên/vai trò** | Nhiều nhãn hoặc vai trò có thể kết hợp | Linh hoạt khi thêm vai trò, khóa ghép chống trùng | Thuộc tính riêng theo vai trò cần thiết kế bổ sung |

Không có quy tắc “disjoint luôn dùng một bảng” hoặc “overlap luôn phải dùng nhiều bảng”. Điều quyết định là **tập trạng thái nghiệp vụ hợp lệ có thể được lưu và kiểm soát nhất quán** với cấu trúc đã chọn hay không.

## 7. Ràng buộc dữ liệu, khóa và chỉ mục

### Ràng buộc ở mức khái niệm và mức vật lý

- **Tư cách kiểu con:** thành viên của mọi kiểu con đều phải tương ứng với một thực thể cha hiện hữu. Trong bảng con, biểu diễn bằng khóa ngoại.
- **Tính duy nhất trong kiểu con:** nếu mỗi người dùng có tối đa một hồ sơ của từng vai trò, dùng khóa chính/unique trên định danh cha trong mỗi bảng con.
- **Tính loại trừ:** không cho phép cùng một thực thể thuộc hai kiểu con bị cấm kết hợp. Ràng buộc hàng đơn như \\(CHECK\\) thường dễ thực hiện khi dữ liệu nằm cùng bảng; nếu tách bảng, cần thiết kế khóa và ràng buộc xuyên bảng phù hợp.
- **Tính bao phủ:** bảo đảm ít nhất một kiểu con khi mô hình là toàn phần. Khóa ngoại thông thường từ con lên cha **không tự kiểm soát được** điều này.
- **Thuộc tính riêng:** chỉ bắt buộc trường dành cho kiểu con thực sự đang áp dụng; tránh yêu cầu tất cả bản ghi có tất cả trường.

Trong PostgreSQL, \\(CHECK\\) chỉ từ chối biểu thức trả về **FALSE**; kết quả **NULL/UNKNOWN** không tự bị từ chối. Vì vậy, khi ràng buộc có cột nullable, cần viết rõ \\(IS NULL\\)/\\(IS NOT NULL\\) hoặc thêm \\(NOT NULL\\), như ví dụ fulfillment.

Nếu kiểm tra điều kiện xuyên nhiều bảng bằng trigger, phải xét **giao dịch đồng thời**: hai giao dịch có thể cùng đọc “chưa tồn tại” rồi cùng thêm hai loại không tương thích. Các phương án đáng tin cậy gồm khóa hàng cha để tuần tự hóa thay đổi, ràng buộc khóa ngoại ghép với discriminator, hoặc cơ chế giao dịch phù hợp; chỉ kiểm tra ở ứng dụng trước khi ghi thường không đủ.

### Chỉ mục theo truy vấn

- Với \\(buyer\_profiles.user\_id\\) và \\(seller\_profiles.user\_id\\), khóa chính đã tạo chỉ mục hỗ trợ JOIN và kiểm tra tồn tại.
- Bảng \\(user\_roles\\) có khóa chính \\((user\_id, role\_code)\\), phù hợp khi liệt kê vai trò của **một** người dùng. Nếu thường xuyên truy vấn tất cả người dùng theo \\(role\_code\\), cân nhắc chỉ mục bổ sung \\((role\_code, user\_id)\\).
- Với bảng chung, có thể lập chỉ mục theo discriminator kết hợp cột lọc/trạng thái thực sự xuất hiện trong truy vấn. Tránh thêm chỉ mục chỉ vì mỗi kiểu con có tên riêng.

~~~sql
-- Hữu ích khi truy vấn theo vai trò rồi lấy các user_id.
CREATE INDEX idx_user_roles_role_user
ON user_roles (role_code, user_id);

-- Đếm số tài khoản có đồng thời cả hai vai trò:
SELECT COUNT(*)
FROM user_roles AS b
JOIN user_roles AS s ON s.user_id = b.user_id
WHERE b.role_code = 'BUYER'
  AND s.role_code = 'SELLER';
~~~

## 8. Khi quan hệ phân loại thay đổi theo thời gian

Mô hình hóa trạng thái hiện tại và mô hình hóa lịch sử là hai bài toán khác nhau. Ví dụ, một người dùng hôm nay chỉ là Buyer, tháng sau trở thành Seller, và tháng tiếp theo ngừng bán. Nếu nghiệp vụ cần biết **người dùng có vai trò gì tại ngày X**, bảng \\(user\_roles\\) hiện tại không đủ.

Khi đó có thể mô hình hóa các đợt hiệu lực:

~~~sql
CREATE TABLE user_role_periods (
    role_period_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id        BIGINT NOT NULL REFERENCES app_users(user_id),
    role_code      TEXT NOT NULL
                   CHECK (role_code IN ('BUYER', 'SELLER')),
    valid_from     TIMESTAMPTZ NOT NULL,
    valid_to       TIMESTAMPTZ,
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);
~~~

Trong ví dụ này, hai **vai trò khác nhau** có thể có khoảng hiệu lực giao nhau. Nếu mỗi người dùng không được có hai khoảng cùng hiệu lực **cho cùng một vai trò**, cần thêm ràng buộc chống giao nhau theo \\((user\_id, role\_code)\\) và khoảng thời gian, chẳng hạn exclusion constraint phù hợp của PostgreSQL, hoặc cơ chế giao dịch tương đương.

Đặc biệt, một thực thể *từng* thuộc hai kiểu con vào **hai thời điểm khác nhau** chưa chứng minh phân cấp chồng lấp tại **cùng một thời điểm**. Phải thống nhất ngữ nghĩa thời gian trước khi kết luận.

## 9. Nhìn sang document, đồ thị và mô hình phân tích

Quy tắc loại trừ/chồng lấp thuộc **nghiệp vụ**, không phụ thuộc hoàn toàn vào công nghệ lưu trữ:

| Hướng lưu trữ | Biểu diễn loại trừ nhau | Biểu diễn chồng lấp | Cần kiểm soát |
| --- | --- | --- | --- |
| **Quan hệ** | Discriminator kết hợp \\(CHECK\\), hoặc bảng con có ràng buộc tương ứng | Nhiều bảng con cùng khóa cha, hoặc bảng liên kết vai trò | Khóa, tính bao phủ, tính loại trừ, giao dịch |
| **Document** | Trường \\(type\\) một giá trị và schema kiểm tra trường phụ thuộc loại | Mảng vai trò và các khối dữ liệu riêng theo vai trò | Giá trị trùng, thiếu dữ liệu theo vai trò, cập nhật document |
| **Đồ thị** | Một node được gắn đúng một nhãn/loại trong nhóm loại trừ theo quy tắc nghiệp vụ | Một node có nhiều label hoặc quan hệ vai trò | Ràng buộc trên tổ hợp nhãn/cạnh, phạm vi và thời gian |
| **Phân tích/warehouse** | Dimension có loại duy nhất khi thật sự loại trừ | Bảng bridge giữa thực thể và nhiều phân loại | Tránh nhân bản số liệu khi JOIN qua nhiều vai trò |

Ví dụ trên document database, người dùng có thể có:

~~~json
{
  "userId": 1,
  "email": "minh@example.test",
  "roles": ["BUYER", "SELLER"],
  "buyerProfile": { "loyaltyPoints": 120 },
  "sellerProfile": { "shopName": "Minh Store" }
}
~~~

Tài liệu này diễn đạt được sự chồng lấp, nhưng cơ chế xác thực schema hoặc logic ghi vẫn phải bảo đảm \\(roles\\) không có giá trị lặp và dữ liệu hồ sơ phù hợp với vai trò. Một mảng nhận tùy ý **không tự bảo đảm** ràng buộc nghiệp vụ.

Trong mô hình phân tích, ví dụ một giao dịch doanh thu nối đến người dùng có cả Buyer và Seller, JOIN trực tiếp qua hai bản ghi vai trò có thể làm **nhân đôi dòng giao dịch** nếu truy vấn tính tổng ở sai mức hạt (*grain*). Cần xác định vai trò đang được phân tích hoặc dùng bridge/điều kiện lọc thích hợp trước khi tổng hợp.

## 10. Những lỗi mô hình hóa thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng một cột \\(user\_type = 'BUYER'/'SELLER'\\) cho người có thể giữ cả hai vai trò | Không lưu được trạng thái chồng lấp | Dùng hồ sơ con hoặc quan hệ nhiều vai trò |
| Đặt hai bảng con cho nhóm loại trừ nhưng chỉ thêm FK tới cha | Cùng ID có thể xuất hiện ở cả hai bảng | Thêm quy tắc loại trừ bằng cấu trúc/ràng buộc dữ liệu phù hợp |
| Nhầm “đúng một” với “tối đa một” | Chấp nhận bản ghi không có kiểu con khi nghiệp vụ bắt buộc phân loại | Xác định thêm ràng buộc toàn phần |
| Suy từ dữ liệu hiện tại rằng các loại loại trừ nhau | Không hỗ trợ trường hợp nghiệp vụ mới hợp lệ | Xác nhận quy tắc từ nghiệp vụ, không suy từ mẫu dữ liệu |
| Nhầm nhiều vai trò của một người với nhiều thực thể người dùng | Nhân bản danh tính và thuộc tính chung | Dùng một khóa cha và nhiều tư cách thành viên |
| Lưu cờ vai trò cùng bảng hồ sơ nhưng không đồng bộ | Cờ báo có vai trò trong khi hồ sơ không tồn tại | Chọn một nguồn sự thật hoặc ràng buộc nhất quán |
| Bỏ qua chiều thời gian hoặc phạm vi | Cấm sai tổ hợp vai trò, mất lịch sử | Xác định hiệu lực theo thời gian/ngữ cảnh nếu cần |
| Dùng \\(JOIN\\) vai trò để tính số liệu mà không kiểm tra mức hạt | Tăng sai doanh thu, số lượng hoặc tần suất | Tổng hợp đúng cấp thực thể/sự kiện, lọc vai trò rõ ràng |

## 11. Quy trình quyết định và tự kiểm tra

Khi gặp một phân cấp mới, có thể đi theo thứ tự:

1. **Xác định kiểu cha và khóa định danh:** một hàng cha đại diện cho đối tượng nào?
2. **Liệt kê kiểu con và thuộc tính riêng:** loại nào có dữ liệu thực sự khác nhau?
3. **Kiểm tra từng cặp kiểu con:** có tổ hợp cùng lúc, cùng phạm vi nào hợp lệ không? Nếu không, ghi rõ *disjoint*; nếu có, ghi rõ *overlapping* hoặc lập ma trận tổ hợp cho các cặp bị cấm cụ thể.
4. **Kiểm tra tính bao phủ:** có bắt buộc ít nhất một kiểu con không?
5. **Chọn ánh xạ vật lý:** một bảng, bảng cha–con hoặc quan hệ vai trò; bảo đảm biểu diễn được tất cả trạng thái hợp lệ.
6. **Định nghĩa và thử ràng buộc:** tạo ca một loại, hai loại, không loại, dữ liệu con thiếu và thay đổi vai trò; thử cả ghi đồng thời nếu có quy tắc xuyên bảng.
7. **Kiểm tra truy vấn và khả năng tiến hóa:** truy vấn theo từng kiểu con, giao của các kiểu, thay đổi loại, thêm kiểu con mới và xử lý lịch sử.

**Bài tự kiểm tra:** Một hệ thống quản lý nhân sự có nhóm \\(Employee\\) với hai kiểu \\(FullTime\\) và \\(PartTime\\). Mỗi nhân viên chỉ có một hợp đồng đang hiệu lực, nhưng một người có thể từng ký hợp đồng cả hai loại ở các giai đoạn khác nhau. Phân cấp này loại trừ hay chồng lấp?

**Gợi ý giải:** Nếu thực thể đang phân loại là **hợp đồng đang hiệu lực**, FullTime và PartTime loại trừ nhau theo quy tắc đã cho. Việc người đó có nhiều loại hợp đồng ở những thời điểm khác nhau không làm thay đổi tính loại trừ tại thời điểm xét. Nếu phân loại là **một người qua toàn bộ lịch sử hợp đồng**, người đó có thể xuất hiện trong cả hai nhóm. Cần chọn đúng thực thể và trục thời gian trước khi quyết định mô hình.

Quy tắc cốt lõi cần giữ trong mọi cách triển khai là: **loại trừ nhau giới hạn số kiểu con đồng thời ở mức tối đa một; chồng lấp cho phép nhiều kiểu con; còn yêu cầu bắt buộc phải thuộc kiểu con nào là một ràng buộc độc lập**.
