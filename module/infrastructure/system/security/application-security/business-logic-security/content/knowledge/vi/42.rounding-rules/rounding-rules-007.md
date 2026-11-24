# Rounding test vectors: thiết kế dữ liệu kiểm thử quy tắc làm tròn

## 1. Test vector phải chứng minh điều gì?

Trong chương **Rounding Rules**, một *rounding test vector* là một ca dữ liệu xác định rõ đầu vào, chính sách làm tròn, kết quả mong đợi và các tác động nghiệp vụ được phép xảy ra.

Một vector tốt không chỉ nói “`1,005` phải ra `1,01`”. Nó còn xác định:

- Giá trị đang là đơn giá, thuế, phí, số tiền thanh toán hay quyền hoàn.
- Loại tiền và đơn vị nhỏ nhất đang áp dụng.
- Làm tròn theo chế độ nào và tại bước nào.
- Kết quả có được ghi tiền hay chỉ dùng để hiển thị.
- Điều gì phải giữ nguyên khi request sai quyền, bị lặp hoặc chạy đồng thời.

Trong bảo mật logic nghiệp vụ, người dùng có thể khai thác chênh lệch làm tròn bằng cách tách dòng hàng, chia thanh toán, gửi nhiều yêu cầu hoàn hoặc chọn đường xử lý có quy tắc có lợi. Mỗi phép tính riêng lẻ có thể đúng nhưng toàn bộ quy trình vẫn tạo thêm tiền, thu thiếu phí hoặc hoàn vượt quyền lợi gốc.

Bài này dùng tiền giả định **U**, quantum hạch toán thông thường là **0,01 U**. Một số vector dùng quantum **0,05 U** để phát hiện việc nhầm số chữ số thập phân với bước tiền được phép. Các mức thuế, phí và khuyến mại đều là chính sách minh họa, không đại diện cho yêu cầu pháp lý hay dữ liệu thị trường.

Trong văn bản, dấu phẩy có thể được dùng để trình bày số thập phân. Trong JSON và mã Java, số được viết bằng chuỗi dùng dấu chấm, chẳng hạn `"1.005"`, để tránh nhầm với dấu phân cách hàng nghìn.

## 2. Chốt hợp đồng trước khi viết kết quả kỳ vọng

### 2.1. Không có một đáp án đúng cho mọi chính sách

Hai hệ thống có thể cùng dùng `HALF_UP` mà vẫn khác tổng thuế:

~~~text
Ba cơ sở tính thuế: 0,05 U; 0,05 U; 0,05 U.
Thuế suất minh họa: 10%.

Làm tròn từng dòng:
  0,01 + 0,01 + 0,01 = 0,03 U.

Làm tròn trên tổng:
  round(0,15 × 10%) = 0,02 U.
~~~

Vector phải ghi rõ cách nào đang được kiểm tra. Không dùng một kết quả kỳ vọng chung cho hai chính sách khác nhau.

Một hợp đồng tối thiểu cần xác định:

| Thành phần | Nội dung phải rõ |
|---|---|
| Miền số | Giá trị âm có hợp lệ ở tầng tiện ích và ở lệnh nghiệp vụ không? |
| Đơn vị | Giá trị theo đơn vị chính hay số nguyên đơn vị nhỏ nhất? |
| Quantum | `0,01`, `0,05` hoặc bước khác |
| Chế độ | `HALF_UP`, `HALF_EVEN`, `DOWN`, `FLOOR` hoặc chế độ cụ thể |
| Điểm làm tròn | Theo đơn vị hàng, theo dòng, theo nhóm hay theo đơn |
| Thứ tự | Giảm giá, phí, thuế và đổi tiền được xử lý theo trình tự nào? |
| Phân bổ | Tổng đã chốt được chia cho các đối tượng ra sao? |
| Phiên bản | Dùng chính sách nào cho giao dịch mới và giao dịch lịch sử? |
| Lỗi | Từ chối, yêu cầu báo giá lại hay trả kết quả cũ trong trường hợp nào? |
| Tác động | Số dư, ledger, quyền hoàn và hạn mức được thay đổi như thế nào? |

Không để fixture mặc định một chế độ khác với mặc định của sản phẩm. Những gì không được ghi rõ trong vector rất dễ bị thư viện, serializer hoặc cơ sở dữ liệu quyết định thay.

### 2.2. Phân biệt các lớp kiểm thử

| Lớp | Đối tượng | Lỗi có thể phát hiện |
|---|---|---|
| Số học | Hàm làm tròn về quantum | Sai nửa đơn vị, sai dấu, nhầm mode |
| Chuỗi tính giá | Giá, giảm giá, phí, thuế | Làm tròn sớm, sai thứ tự, sai phạm vi |
| Phân bổ | Chia một tổng đã chốt | Mất phần dư, chia vượt tổng, phá hòa không ổn định |
| Nghiệp vụ | Thu, hoàn, đảo | Dùng lại quyền lợi hoặc tính lại dữ liệu gốc sai |
| Transaction | Nhiều cập nhật liên quan | Ghi tiền một phần, mất cập nhật, race condition |
| Giao tiếp | JSON, cột dữ liệu, gateway | Mất độ chính xác, cắt phần lẻ, tràn số |
| Quyền đối tượng | Actor, tenant và giao dịch | Tính tiền đúng nhưng thu hoặc hoàn sai quyền |

Một bộ kiểm thử chỉ có phép gọi `setScale` không chứng minh được bảo mật của endpoint thanh toán.

## 3. Cấu trúc một test vector có thể bảo trì

Ví dụ dữ liệu cho một ca ở tầng số học:

~~~json
{
  "id": "ROUND_HALF_UP_POSITIVE_TIE",
  "vectorVersion": "1",
  "operation": "ROUND_TO_QUANTUM",
  "policyVersion": "U_ROUNDING_V1",
  "input": {
    "amount": "1.005",
    "currency": "U",
    "quantum": "0.01",
    "roundingMode": "HALF_UP"
  },
  "expected": {
    "outcome": "ACCEPT",
    "amount": "1.01"
  },
  "reason": "Giá trị nằm đúng giữa hai mức và được làm tròn xa số 0."
}
~~~

Vector nghiệp vụ cần thêm trạng thái ban đầu và trạng thái sau xử lý:

~~~json
{
  "id": "PARTIAL_REFUND_SECOND_UNIT",
  "vectorVersion": "1",
  "operation": "REFUND_EQUAL_UNIT",
  "policyVersion": "U_CUMULATIVE_REFUND_V1",
  "initial": {
    "currency": "U",
    "refundableTotal": "0.05",
    "originalQuantity": 3,
    "acceptedReturnedQuantity": 1,
    "refundedAmount": "0.02",
    "reservedRefundAmount": "0.00"
  },
  "command": {
    "returnQuantity": 1,
    "idempotencyKey": "refund-second-unit"
  },
  "expected": {
    "outcome": "ACCEPT",
    "refundDelta": "0.01",
    "acceptedReturnedQuantity": 2,
    "refundedAmount": "0.03",
    "newCommittedRefundOperations": 1
  }
}
~~~

Ví dụ thứ hai giả định lần hoàn được xử lý thành công và không có phí không hoàn được. Nếu xử lý qua hệ thống ngoài, vector phải phân biệt khoản hoàn đã hoàn tất với quyền hoàn đang được dành cho lệnh chưa rõ kết quả.

Số tiền được lưu dưới dạng chuỗi thập phân để fixture không bị đọc qua số thực nhị phân trước khi đến code kiểm thử. Nếu dùng số nguyên đơn vị nhỏ nhất, vẫn cần chọn biểu diễn đủ phạm vi cho công cụ đọc fixture; không mặc định mọi số nguyên JSON đều được giữ chính xác bởi mọi runtime.

Một vector cũng nên có lý do tồn tại hoặc quy tắc mà nó bảo vệ. Khi chính sách thay đổi, người bảo trì sẽ biết cần sửa kỳ vọng có chủ đích hay cần giữ vector như bằng chứng tương thích lịch sử.

## 4. Nhóm vector số học: ranh giới, dấu và quantum

### 4.1. Trước, đúng và sau nửa đơn vị

Với quantum `0.01`, các giá trị dưới đây phải được tạo từ chuỗi thập phân chính xác.

| ID | Input | Mode | Expected |
|---|---:|---|---:|
| P01 | `1.0049` | `HALF_UP` | `1.00` |
| P02 | `1.005` | `HALF_UP` | `1.01` |
| P03 | `1.0051` | `HALF_UP` | `1.01` |
| N01 | `-1.0049` | `HALF_UP` | `-1.00` |
| N02 | `-1.005` | `HALF_UP` | `-1.01` |
| N03 | `-1.0051` | `HALF_UP` | `-1.01` |

`HALF_UP` chọn mức gần nhất; tại điểm giữa, làm tròn xa số không. Nó không có nghĩa là luôn hướng về phía dương.

Mỗi ranh giới quan trọng nên có bộ ba “ngay dưới, đúng tại, ngay trên”. Chỉ kiểm tra số đúng nửa đơn vị có thể bỏ sót lỗi so sánh `>` với `>=` hoặc lỗi cắt phần lẻ trước khi chọn mức.

### 4.2. Phát hiện nhầm chế độ

| ID | Input | Mode | Expected, quantum `0.01` |
|---|---:|---|---:|
| M01 | `1.005` | `HALF_EVEN` | `1.00` |
| M02 | `1.015` | `HALF_EVEN` | `1.02` |
| M03 | `1.025` | `HALF_EVEN` | `1.02` |
| M04 | `-1.015` | `HALF_EVEN` | `-1.02` |
| M05 | `1.005` | `HALF_DOWN` | `1.00` |
| M06 | `-1.005` | `HALF_DOWN` | `-1.00` |
| M07 | `0.0001` | `UP` | `0.01` |
| M08 | `-0.0001` | `UP` | `-0.01` |
| M09 | `1.009` | `DOWN` | `1.00` |
| M10 | `-1.009` | `DOWN` | `-1.00` |
| M11 | `1.001` | `CEILING` | `1.01` |
| M12 | `-1.001` | `CEILING` | `-1.00` |
| M13 | `1.001` | `FLOOR` | `1.00` |
| M14 | `-1.001` | `FLOOR` | `-1.01` |

Các ca âm đặc biệt quan trọng vì `FLOOR` không giống `DOWN` và `CEILING` không giống `UP`.

Việc tầng số học chấp nhận số âm không đồng nghĩa lệnh thu tiền được nhận amount âm. Bộ vector ở tầng API cần kiểm tra riêng điều kiện của lệnh.

### 4.3. Quantum không phải lũy thừa của mười

Nếu chỉ gọi `setScale(2)`, nhiều giá trị dưới đây sẽ sai vì scale hai không bảo đảm là bội số của `0.05`.

| ID | Input | Quantum | Mode | Expected |
|---|---:|---:|---|---:|
| Q01 | `1.02` | `0.05` | `HALF_UP` | `1.00` |
| Q02 | `1.025` | `0.05` | `HALF_UP` | `1.05` |
| Q03 | `1.025` | `0.05` | `HALF_EVEN` | `1.00` |
| Q04 | `1.075` | `0.05` | `HALF_EVEN` | `1.10` |
| Q05 | `-1.025` | `0.05` | `HALF_UP` | `-1.05` |

Với `HALF_EVEN`, tính chẵn lẻ áp dụng trên số đơn vị quantum. Trong Q03, hai mức lân cận tương ứng 20 và 21 quantum, nên chọn 20. Trong Q04, hai mức là 21 và 22 quantum, nên chọn 22.

Thêm vector từ chối quantum bằng không, âm hoặc ngoài miền sản phẩm hỗ trợ. Không để quantum không hợp lệ dẫn tới phép chia lỗi rồi fallback sang “giữ nguyên giá”.

### 4.4. Kiểm tra không được làm tròn ngầm

Nếu hợp đồng yêu cầu đầu vào đã theo quantum `0.01`:

~~~text
Input 1.2300: hợp lệ về giá trị, không cần bỏ phần giá trị khác không.
Input 1.231: cần làm tròn, phải bị từ chối.
~~~

Ở tầng `BigDecimal` với `UNNECESSARY`, ca thứ hai có thể tương ứng `ArithmeticException`. Ở tầng nghiệp vụ, nên có mã lỗi hoặc loại lỗi đã quy định. Đừng buộc mọi tầng phải lộ cùng exception kỹ thuật.

Cũng cần ca bằng không, đúng một quantum và số nguyên lớn. Nếu sản phẩm chuẩn hóa số không thành `"0.00"`, kiểm tra biểu diễn đó riêng; số không âm trong dữ liệu đầu vào không nên vô tình tạo thêm một giá trị tiền tệ có nghĩa khác.


## 5. Java: chạy cùng một tập vector qua API làm tròn

### 5.1. Kỳ vọng phải là dữ liệu độc lập

Ví dụ sau dùng parameterized test của JUnit. `MoneyRounding.roundToQuantum` đại diện cho API làm tròn thực tế của ứng dụng; khi áp dụng, thay bằng adapter tới code cần kiểm tra. Bài không cung cấp phần cài đặt hàm sản phẩm.

Các expected được ghi trực tiếp trong vector, không được gọi lại chính hàm đang kiểm thử để tạo expected.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.stream.Stream;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RoundingVectorsTest {
    record RoundCase(
            String id,
            String input,
            String quantum,
            RoundingMode mode,
            String expected) {

        @Override
        public String toString() {
            return id;
        }
    }

    static Stream<RoundCase> roundingCases() {
        return Stream.of(
                new RoundCase("below-positive-tie",
                        "1.0049", "0.01", RoundingMode.HALF_UP, "1.00"),
                new RoundCase("positive-tie",
                        "1.005", "0.01", RoundingMode.HALF_UP, "1.01"),
                new RoundCase("negative-tie",
                        "-1.005", "0.01", RoundingMode.HALF_UP, "-1.01"),
                new RoundCase("half-even-even-neighbor",
                        "1.005", "0.01", RoundingMode.HALF_EVEN, "1.00"),
                new RoundCase("half-even-next-even-neighbor",
                        "1.015", "0.01", RoundingMode.HALF_EVEN, "1.02"),
                new RoundCase("ceiling-negative",
                        "-1.001", "0.01", RoundingMode.CEILING, "-1.00"),
                new RoundCase("floor-negative",
                        "-1.001", "0.01", RoundingMode.FLOOR, "-1.01"),
                new RoundCase("down-negative",
                        "-1.009", "0.01", RoundingMode.DOWN, "-1.00"),
                new RoundCase("cash-quantum-half-up",
                        "1.025", "0.05", RoundingMode.HALF_UP, "1.05"),
                new RoundCase("cash-quantum-half-even",
                        "1.025", "0.05", RoundingMode.HALF_EVEN, "1.00"),
                new RoundCase("already-exact",
                        "1.2300", "0.01", RoundingMode.UNNECESSARY, "1.23")
        );
    }

    @ParameterizedTest(name = "{0}")
    @MethodSource("roundingCases")
    void roundsAccordingToVector(RoundCase vector) {
        BigDecimal actual = MoneyRounding.roundToQuantum(
                new BigDecimal(vector.input()),
                new BigDecimal(vector.quantum()),
                vector.mode());

        BigDecimal expected = new BigDecimal(vector.expected());

        assertEquals(
                0,
                expected.compareTo(actual),
                vector.id());
    }
}
~~~

Đoạn mã minh họa cấu trúc test, không phải bộ test hoàn chỉnh có thể chạy độc lập khi chưa có API sản phẩm và cấu hình dự án.

### 5.2. So sánh giá trị khác so sánh biểu diễn

`BigDecimal("1.0")` và `BigDecimal("1.00")` có cùng giá trị số nhưng khác scale. Dùng `compareTo` trong nhóm vector kiểm tra giá trị giúp tránh gắn quy tắc định dạng vào phép tính số.

Nếu API quy định phải trả chuỗi `"1.00"`, cần kiểm thử serializer hoặc adapter riêng. Khi đó scale hoặc chuỗi canonical là một phần hợp đồng và phải được assert rõ.

Không sửa expected từ `"1.00"` thành `"1.0"` chỉ để làm một test định dạng pass nếu hợp đồng bên ngoài yêu cầu hai chữ số. Ngược lại, cũng không báo sai tiền chỉ vì một hàm nội bộ trả cùng giá trị với scale khác khi scale không thuộc hợp đồng hàm đó.

### 5.3. Lỗi phải được kiểm tra theo đúng tầng

Bổ sung các ca:

~~~text
ROUND_TO_QUANTUM("1.231", "0.01", UNNECESSARY)
  → lỗi cần làm tròn theo hợp đồng của API số học.

ROUND_TO_QUANTUM("1.00", "0.00", HALF_UP)
  → lỗi quantum không hợp lệ.

CHARGE(amount="-1.00")
  → từ chối lệnh thu tiền, dù hàm số học biết xử lý số âm.

CHARGE(rawAmount="0.004", quantum="0.01", HALF_UP)
  → giá trị làm tròn bằng 0;
    nếu hợp đồng thu yêu cầu tiền chính thức > 0, phải từ chối.
~~~

Một sản phẩm có giao dịch miễn phí hợp lệ cần quy tắc khác ở ca cuối. Không dùng một expected “luôn lỗi khi ra số không” cho mọi lệnh, như dòng hàng tặng hoặc khoản điều chỉnh không phát sinh tiền.

## 6. Nhóm vector cho điểm làm tròn và chuỗi tính giá

### 6.1. Chọn dữ liệu làm hai cách tính khác nhau

Nếu dùng toàn giá trị nguyên đơn vị nhỏ nhất và tỷ lệ tạo kết quả tròn, test sẽ không phát hiện việc chuyển phép làm tròn từ cuối tổng vào từng dòng.

Các vector phân biệt nên đặt giá trị sát nửa quantum hoặc tạo ra nhiều phần dư:

| ID | Dữ liệu và chính sách | Expected chính |
|---|---|---|
| PIPE01 | Đơn giá `1.005`, số lượng 3, làm tròn sau phép nhân, `HALF_UP` | Tổng dòng `3.02` |
| PIPE02 | Ba cơ sở `0.05`, thuế 10%, làm tròn tổng nhóm | Thuế `0.02` |
| PIPE03 | Cùng cơ sở, nhưng chính sách tính thuế riêng từng dòng | Thuế `0.03` |
| PIPE04 | Gross `0.15`, giảm 10% trên đơn, thuế 10% sau giảm | Discount `0.02`, net `0.13`, tax `0.01`, payable `0.14` |
| PIPE05 | Giá trị `1.0049` làm tròn trực tiếp về `0.01` | `1.00` |
| PIPE06 | Cộng chính xác `0.10` và `0.20` rồi chuẩn hóa | `0.30` |

PIPE05 phải phát hiện cách tính sai:

~~~text
roundTo3(1,0049) = 1,005
roundTo2(1,005)  = 1,01

Trong khi:
roundTo2(1,0049) = 1,00
~~~

Đó là làm tròn hai lần ở hai độ chia khác nhau. Chỉ kiểm tra `R(R(x)) = R(x)` với cùng quantum sẽ không phát hiện trường hợp này.

### 6.2. Vector phải nêu cả điểm làm tròn

Với PIPE04, snapshot kỳ vọng có thể là:

~~~json
{
  "id": "ORDER_DISCOUNT_THEN_GROUP_TAX",
  "policyVersion": "U_ORDER_V1",
  "input": {
    "lines": [
      {"lineId": "A", "unitPrice": "0.05", "quantity": 1},
      {"lineId": "B", "unitPrice": "0.05", "quantity": 1},
      {"lineId": "C", "unitPrice": "0.05", "quantity": 1}
    ],
    "discountRate": "0.10",
    "taxRate": "0.10"
  },
  "roundingPoints": {
    "gross": "AFTER_SUM_OF_RAW_LINES",
    "discount": "ORDER_TOTAL",
    "tax": "GROUP_TOTAL_AFTER_DISCOUNT"
  },
  "expected": {
    "gross": "0.15",
    "discount": "0.02",
    "net": "0.13",
    "tax": "0.01",
    "payable": "0.14"
  }
}
~~~

Trường `roundingPoints` là dữ liệu mô tả test, không phải quyền cho client quyết định cách tính ở API thật. Adapter của test cần chọn policy server tương ứng.

Đừng chỉ assert `payable`. Hai thành phần sai có thể bù nhau và tạo tổng cuối đúng. Cần kiểm tra gross, discount, net, tax, fee và những phân bổ có ý nghĩa đối với hoàn hoặc đối soát.

### 6.3. Kiểm tra tách, gộp và phạm vi kinh tế

Giả sử khuyến mại tính trên cả đơn:

~~~text
Biến thể A: một dòng số lượng 3.
Biến thể B: ba dòng tương đương, mỗi dòng số lượng 1.
~~~

Nếu cả hai đại diện cho cùng nhóm giá có thẩm quyền của server, kết quả khuyến mại không được thay đổi chỉ vì client đổi cách nhóm JSON.

Tuy nhiên, ba dòng có thuế, người bán hoặc điều kiện khuyến mại khác nhau không nhất thiết được gộp. Fixture cần ghi các thuộc tính phân nhóm, thay vì ngầm coi cùng mã sản phẩm là đủ.

Một vector phí minh họa:

~~~text
Phí 1% trên một đơn 0,50 U:
  round(0,005) = 0,01 U.

Client chia việc thanh toán thành hai request 0,25 U.
Nếu phí vẫn thuộc phạm vi đơn:
  tổng phí của đơn phải vẫn là 0,01 U,
  không tính độc lập hai lần 0,0025 rồi làm tròn thành 0.
~~~

Nếu sản phẩm thật sự định nghĩa phí trên từng thanh toán, kết quả có thể khác. Bộ vector phải bảo vệ chính sách đã chọn, không tạo một invariant tách/gộp không tồn tại trong sản phẩm.

## 7. Nhóm vector phân bổ phần dư

### 7.1. Tổng đã chốt không được bị thay đổi khi chia nhỏ

Trong mục này, tổng A và các kết quả được biểu diễn bằng **số nguyên đơn vị quantum**. Quantum là `0.01 U`, nên A = 2 nghĩa là `0.02 U`.

Giả sử dùng phương pháp phần dư lớn nhất: cấp phần nguyên theo tỷ lệ, rồi cấp từng đơn vị còn lại cho phần dư lớn nhất. Khi bằng nhau, dùng ID dòng ổn định theo thứ tự A, B, C.

| ID | Tổng A | Trọng số A, B, C | Expected theo A, B, C |
|---|---:|---|---|
| AL01 | 2 | `1, 1, 1` | `1, 1, 0` |
| AL02 | 5 | `1, 1, 1` | `2, 2, 1` |
| AL03 | 1 | `4, 4, 5` | `0, 0, 1` |
| AL04 | 3 | `0, 5, 0` | `0, 3, 0` |
| AL05 | 0 | `1, 1, 1` | `0, 0, 0` |

Với tổng dương và tổng trọng số bằng không, expected phải là lỗi theo chính sách phân bổ, không chia cho không hoặc âm thầm giữ tiền trong một dòng tùy chọn.

Vector có trọng số âm phải bị từ chối trong mô hình phân bổ không âm này. Khoản đảo hoặc phân bổ âm cần hợp đồng riêng, không tự đưa vào thuật toán rồi dùng floor như với số dương.

### 7.2. Kiểm tra bản đồ phân bổ, không chỉ tổng

Với AL01, cần assert:

~~~text
allocation["A"] = 1
allocation["B"] = 1
allocation["C"] = 0
sum(allocation) = 2
~~~

Nếu chỉ assert tổng bằng hai, một cài đặt có thể cấp toàn bộ cho một dòng không đủ điều kiện mà vẫn pass.

Tạo biến thể đảo thứ tự đầu vào `C, B, A` nhưng giữ nguyên ID và thuộc tính kinh tế. Kết quả theo ID vẫn phải là `A=1, B=1, C=0`. Điều này phát hiện việc dùng vị trí trong request làm quy tắc phá hòa.

Nếu client có thể tạo tùy ý ID hoặc ranh giới dòng, tính ổn định của thuật toán chưa đủ. Cần vector ở tầng nghiệp vụ chứng minh không thể tạo thêm dòng chỉ để nhận ưu tiên phân bổ ngoài chính sách.

### 7.3. Chứng minh phần dư bằng số chính xác

Với tổng A và trọng số nguyên `w_i`, `W = tổng w_i`:

~~~text
base_i = floor(A × w_i / W)
remainder_i = (A × w_i) mod W
leftover = A - sum(base_i)
~~~

Đây là một cách lập luận độc lập để xác định expected. Không cần cắt tỷ lệ `1/3` thành một số thập phân hữu hạn rồi so sánh phần dư xấp xỉ.

Test nên có trọng số lớn để phát hiện tràn ở phép nhân `A × w_i` nếu cài đặt dùng kiểu nguyên hữu hạn. Phạm vi dữ liệu phải được xác định trước; không bắt một API có giới hạn nhỏ xử lý mọi số nguyên tùy ý.

Khi có trần theo dòng hoặc nhóm đủ điều kiện riêng, bổ sung vector theo đúng thuật toán có trần của sản phẩm. Phải kiểm tra đồng thời tổng, trần và tập nhận tiền. Không coi việc cắt các phần vượt trần sau phân bổ là đủ nếu nó làm mất phần dư.


## 8. Nhóm vector hoàn, đảo và quyền lợi cộng dồn

### 8.1. Một fixture gốc cho nhiều chuỗi hoàn

Giả sử ba đơn vị giống nhau có tổng tiền được phép hoàn là `0.05 U`, không có phí không hoàn được. Chính sách dùng quyền hoàn lũy kế:

~~~text
E(k) = round(0,05 × k / 3), theo HALF_UP và quantum 0,01.
refundDelta = E(k_mới) - E(k_cũ).
~~~

Các expected cố định:

| Tổng đơn vị đã trả k | E(k) |
|---|---:|
| 0 | `0.00` |
| 1 | `0.02` |
| 2 | `0.03` |
| 3 | `0.05` |

Các chuỗi cần kiểm tra:

| ID | Chuỗi số lượng trả | Số tiền hoàn theo từng bước | Tổng cuối |
|---|---|---|---:|
| RF01 | `1, 1, 1` | `0.02, 0.01, 0.02` | `0.05` |
| RF02 | `2, 1` | `0.03, 0.02` | `0.05` |
| RF03 | `1, 2` | `0.02, 0.03` | `0.05` |
| RF04 | `3` | `0.05` | `0.05` |

Mỗi chuỗi có thể có số tiền từng request khác nhau. Điều cần giữ là quyền lợi lũy kế tại cùng số lượng đã được chấp nhận và tổng cuối, không phải mọi request đều nhận cùng số tiền.

Cách tính sai `round(0.05 / 3)` cho mỗi request sẽ tạo ba lần `0.02`, tổng `0.06`. RF01 phải phát hiện được lỗi này.

Fixture còn cần ghi trạng thái giao dịch gốc và quyền của người yêu cầu. Một người không có quyền không được nhận `0.01` chỉ vì đó là phần chênh lệch hợp lệ của một chuỗi hoàn.

### 8.2. Phân biệt đã hoàn và đang dành quyền hoàn

Thêm trạng thái:

~~~text
refundableTotal
refundedCommitted
refundReserved
acceptedReturnedQuantity
returnUnits hoặc tham chiếu quyền lợi đã được tiêu thụ
~~~

Một lệnh hoàn chưa rõ kết quả bên ngoài có thể đã giữ quyền hoàn. Vector phải bảo đảm request mới không dùng lại phần đó.

Ví dụ, toàn bộ quyền hoàn `0.05` đang dành cho một lệnh chưa rõ kết quả. Expected của request muốn hoàn thêm không thể là tiếp tục cấp `0.05` chỉ vì `refundedCommitted` vẫn bằng không.

Cần kiểm tra cả khả năng retry cùng lệnh. Retry có thể trả trạng thái đang xử lý thay vì tạo khoản giữ quyền hoàn mới.

### 8.3. Không đổi dữ liệu lịch sử theo cấu hình mới

Tạo giao dịch bằng `U_REFUND_V1`, sau đó đổi cấu hình giá hoặc chế độ làm tròn cho giao dịch mới. Yêu cầu hoàn giao dịch cũ phải dùng quyền lợi hoặc chính sách lịch sử mà sản phẩm đã cam kết.

Vector cần lưu rõ:

~~~text
originalPricingSnapshotId
originalPolicyVersion
currentPolicyVersion
expectedRefundableComponents
expectedRefundAmount
~~~

Không tạo expected bằng cấu hình hiện hành rồi coi khác biệt lịch sử là một lỗi cần sửa.

### 8.4. Ca đảo phải dùng số tiền đã ghi nhận

Với `CEILING`, giá trị thô `0.005` được chốt thành `0.01`. Nếu đảo toàn bộ khoản đã ghi nhận, số tiền đối ứng phải phản ánh `-0.01` trong quy ước delta của ví dụ.

Một cài đặt sai có thể tính:

~~~text
CEILING(-0,005) = 0,00
~~~

Vector đảo cần expected theo số đã hạch toán, không theo cách làm tròn lại số thô âm. Quy tắc debit, credit và tài khoản đối ứng cụ thể vẫn phụ thuộc mô hình ledger.

## 9. Nhóm vector về quyền, idempotency và transaction

### 9.1. Tính đúng tiền chưa đủ để được phép ghi tiền

Dùng fixture thanh toán đơn giản theo ví dụ PIPE04:

~~~text
Tenant T1.
Người mua A có số dư khả dụng 1,00 U.
Quote Q1 có payable 0,14 U, net cho người bán 0,13 U, thuế 0,01 U.
Chưa có lệnh thu thành công cho ý định thanh toán này.
Không có phí hoặc tài trợ bên ngoài.
~~~

Một lần thu được phép có thể tạo các delta cùng loại tiền:

~~~text
Tài khoản người mua: -0,14 U.
Khoản được hưởng của người bán: +0,13 U.
Nghĩa vụ thuế: +0,01 U.
~~~

Tổng delta bằng không trong mô hình minh họa này. Không cần ép số lượng dòng ledger nếu cài đặt có cấu trúc sổ khác; kiểm tra những delta và quan hệ nghiệp vụ có ý nghĩa.

| ID | Thay đổi từ fixture | Expected về quyền và tiền |
|---|---|---|
| SEC01 | Chủ thể được phép xác nhận Q1 | Một lần thu; người mua còn `0.86`; các thành phần nhận đúng phần |
| SEC02 | Actor khác không có quyền trên Q1 | Từ chối; không có biến động tiền |
| SEC03 | Actor đưa quote hoặc tài khoản của tenant khác | Từ chối và không lộ dữ liệu ngoài phạm vi |
| SEC04 | Client gửi payable `0.13` thay vì `0.14` | Không ghi tiền theo tổng client; xử lý lệch xác nhận theo hợp đồng |
| SEC05 | Client đổi rounding mode hoặc quantum | Không thay policy server |
| SEC06 | Sửa số lượng sau khi đã phê duyệt snapshot | Không dùng phê duyệt cũ cho nội dung mới ngoài chính sách |
| SEC07 | Actor chỉ có quyền xem hóa đơn | Không được thu, điều chỉnh hoặc hoàn |

Đối với request bị từ chối, audit từ chối có thể được ghi. Expected “không thay đổi” phải nhắm vào tiền, quyền lợi và dữ liệu nghiệp vụ liên quan, không cấm mọi dấu vết vận hành.

### 9.2. Vector idempotency cần kiểm tra kết quả bền vững

Một phạm vi khóa minh họa là:

~~~text
tenantId + actorId + operationType + idempotencyKey
~~~

Đây là lựa chọn thiết kế, không phải phạm vi bắt buộc cho mọi hệ thống. Fixture phải phù hợp với phạm vi của sản phẩm.

| ID | Chuỗi thao tác | Expected |
|---|---|---|
| ID01 | Gửi cùng lệnh, cùng khóa hai lần | Một tác động tiền tệ, kết quả tham chiếu cùng giao dịch |
| ID02 | Cùng khóa nhưng đổi snapshot hoặc nội dung có ảnh hưởng | Xung đột, không có tác động mới |
| ID03 | Cùng chuỗi khóa nhưng actor hoặc tenant khác | Không đọc hay chiếm kết quả ngoài quyền |
| ID04 | Timeout phía client sau commit rồi retry | Trả giao dịch đã commit, không tính hoặc thu lại |
| ID05 | Retry sau khi policy hiện hành đã đổi | Không thay số tiền của lệnh cũ đã commit |
| ID06 | Đổi khóa để thu toàn phần lại cùng ý định chỉ được thu một lần | Ràng buộc nghiệp vụ ngăn lần thu thứ hai |

ID06 không áp dụng nguyên xi cho sản phẩm cho phép nhiều lần thu hợp lệ. Khi có thanh toán từng phần, cần định danh và hạn mức của các phần đó.

Không chỉ assert response của hai request giống nhau. Hai response có thể giống nhau nhưng mỗi request vẫn đã ghi một bộ bút toán. Kiểm tra số lệnh nghiệp vụ đã commit, số dư cuối và delta ledger.

### 9.3. Vector đồng thời phải nêu điểm gặp nhau

Một vector concurrency cần có lịch tương tác hoặc barrier:

~~~text
Hai transaction cùng sẵn sàng xử lý.
Buộc chúng gặp nhau trước ranh giới cập nhật cần bảo vệ.
Cho tiếp tục.
Đợi cả hai hoàn tất.
Đọc lại trạng thái bền vững.
~~~

Các ca điển hình:

| ID | Hai thao tác cùng chạy | Expected |
|---|---|---|
| CC01 | Cùng lệnh thu, cùng khóa | Một tác động tiền tệ |
| CC02 | Khác khóa nhưng cùng ý định chỉ được thu một lần | Không có lần thu thứ hai |
| CC03 | Hoàn cùng một đơn vị hàng, khác khóa | Không tiêu thụ quyền lợi của đơn vị đó hai lần |
| CC04 | Hoàn hai đơn vị khác nhau từ fixture RF, mỗi request một đơn vị | Có thể cả hai thành công; tổng hoàn sau hai đơn vị là `0.03` |
| CC05 | Một lệnh hoàn và một lệnh thay đổi trạng thái liên quan | Tuân theo thứ tự hiệu lực đã định nghĩa, không dựa vào trạng thái cũ ngoài ranh giới nhất quán |

Trong CC04, không nên viết expected rằng chỉ một request được thành công. Hai quyền hoàn khác nhau đều có thể hợp lệ. Điều cần bảo vệ là cập nhật cộng dồn được tuần tự hóa đúng; các phần có thể là `0.02` và `0.01` theo thứ tự được chấp nhận.

Nếu cả hai transaction cùng đọc k = 0 rồi đều hoàn `0.02`, tổng `0.04` chưa vượt trần `0.05` nhưng đã vượt E(2) = `0.03`. Đây là lý do kiểm tra trần tổng không thay thế kiểm tra quyền lợi cộng dồn.

Chạy hai request nối tiếp không kiểm chứng được những ca này. Dùng độ trễ ngẫu nhiên cũng khó tạo bằng chứng ổn định về đúng điểm xung đột.

### 9.4. Vector lỗi giữa chừng

Chèn lỗi có kiểm soát trong môi trường kiểm thử tại các điểm như:

~~~text
Sau cập nhật số dư nhưng trước ghi ledger.
Sau tiêu thụ quyền hoàn nhưng trước lưu kết quả lệnh.
Trước commit.
Sau commit nhưng trước trả response.
~~~

Các lỗi trước commit phải không để lại tác động tiền tệ một phần. Lỗi sau commit phải cho phép retry tìm lại kết quả cũ.

Với hệ thống ngoài, transaction cục bộ không bao trùm lời gọi HTTP. Expected phải bao gồm trạng thái chưa rõ kết quả, phần quyền lợi đang giữ và quy trình đối soát, thay vì mặc định mọi exception đều có thể rollback khoản tiền đã chuyển bên ngoài.

## 10. Nhóm vector biểu diễn, giới hạn và đầu vào lỗi

### 10.1. Chuyển đổi đơn vị không được làm tròn lần nữa

Nếu số tiền đã được chốt theo `0.01 U`, việc chuyển sang số nguyên đơn vị nhỏ nhất phải là phép chuyển đổi chính xác.

| ID | Input tại adapter, scale hai | Expected |
|---|---|---|
| IO01 | `"1.23"` | `123` đơn vị nhỏ nhất |
| IO02 | `"1.2300"` | `123`, nếu hợp đồng chấp nhận trailing zero |
| IO03 | `"1.231"` | Từ chối vì còn phần lẻ, không cắt thành `123` |
| IO04 | `"92233720368547758.07"` | `9223372036854775807` nếu adapter hỗ trợ toàn phạm vi long |
| IO05 | `"92233720368547758.08"` | Lỗi tràn long |
| IO06 | `"92233720368547758.075"` được HALF_UP về scale hai | Giá trị thành `92233720368547758.08`, sau đó lỗi tràn khi chuyển sang long |

IO04 kiểm tra phạm vi kỹ thuật của adapter, không khẳng định sản phẩm được phép giao dịch một số tiền lớn như vậy. Lệnh nghiệp vụ có thể phải từ chối sớm hơn theo hạn mức.

Trong Java, `movePointRight(2).longValueExact()` trên số tiền phù hợp có thể giúp phát hiện phần lẻ và tràn. `longValue()` không có cùng hợp đồng. Con số hai ở đây thuộc mô hình minh họa, không áp dụng cho mọi loại tiền.

### 10.2. Parser và serializer cũng cần vector

Nếu schema tiền tệ quy định chuỗi thập phân chuẩn dùng dấu chấm và không hỗ trợ ký pháp số mũ, các input như sau phải bị từ chối theo schema:

~~~text
"1,23"
"1e3"
"NaN"
"Infinity"
chuỗi rỗng
giá trị null
chuỗi vượt số chữ số hoặc scale cho phép
~~~

Một API khác có thể hỗ trợ một số cách viết khác. Điểm quan trọng là expected được gắn với schema đã công bố, không phụ thuộc việc một parser ngẫu nhiên có đọc được hay không.

Giá trị có quá nhiều chữ số hoặc exponent cực lớn cần bị chặn trước khi tạo phép tính ngoài phạm vi hỗ trợ. Không cần dùng một input tiêu tốn tài nguyên không giới hạn để kiểm thử; đặt vector ngay dưới, đúng tại và ngay trên giới hạn đã chọn.

Kiểm thử cả vòng truyền dữ liệu:

~~~text
Chuỗi fixture chính xác
  → DTO
  → giá trị tiền nội bộ
  → cột dữ liệu
  → đọc lại
  → payload gateway hoặc response
~~~

Một unit test số học pass không phát hiện serializer vô tình chuyển sang `double` hoặc cột dữ liệu tự thay scale. Kiểm tra lại giá trị tại các ranh giới đó.

Nếu hợp đồng yêu cầu output `"1.00"`, kiểm tra chuỗi. Nếu hợp đồng chỉ yêu cầu giá trị số, không áp đặt định dạng từ tầng hiển thị vào dữ liệu nội bộ.


## 11. Tạo oracle độc lập và những tính chất có điều kiện

### 11.1. Tránh kiểm thử tự xác nhận chính nó

*Oracle* là căn cứ xác định kết quả nào đúng. Nếu expected và actual đều gọi cùng logic sản phẩm, test có thể pass ngay cả khi logic đó sai.

Ví dụ không có giá trị xác minh độc lập:

~~~java
BigDecimal expected = pricingService.calculate(input);
BigDecimal actual = pricingService.calculate(input);

assertEquals(expected, actual);
~~~

Tương tự, dùng cùng helper làm tròn sai trong cả hàm sản phẩm và hàm sinh expected sẽ che lỗi.

Một cách xây dựng expected phù hợp:

1. Bắt đầu từ hợp đồng nghiệp vụ và phiên bản chính sách.
2. Chọn các giá trị nhỏ để có thể kiểm tra bằng số thập phân hoặc phân số chính xác.
3. Ghi expected cố định và giải thích ngắn vì sao có kết quả đó.
4. Với phân bổ, dùng thương nguyên và phần dư để kiểm chứng.
5. Với một chuỗi hoàn, kiểm tra cả các mốc quyền lợi lũy kế và tổng cuối.
6. Khi dùng công cụ tính tham chiếu, bảo đảm nó không chỉ tái sử dụng chính code cần kiểm tra.

Quan hệ giữa các phần có thể hình dung như sau:

~~~mermaid
flowchart TD
    P[Hợp đồng và phiên bản chính sách] --> O[Tính kỳ vọng độc lập]
    P --> I[Cài đặt sản phẩm]
    O --> V[Vector có expected cố định]
    V --> A[So sánh kết quả và trạng thái]
    I --> A
    A --> S[Kiểm tra số dư, ledger, quyền lợi và số lần thực hiện]
~~~

Khi actual khác expected, cần phân biệt lỗi cài đặt với thay đổi chính sách đã được chấp nhận. Không tự cập nhật toàn bộ expected từ kết quả hiện tại của ứng dụng.

### 11.2. Property test bổ sung cho vector cố định

Các tính chất số học hữu ích, trong miền giá trị và quantum được hỗ trợ:

~~~text
R_q(x) là một bội số của q.
R_q(R_q(x)) = R_q(x), với cùng q và cùng mode.
Nếu x đã là bội số của q thì R_q(x) = x.
Với chế độ làm tròn gần nhất: |R_q(x) - x| <= q / 2.
~~~

Với `UNNECESSARY`, giá trị không biểu diễn được đúng theo quantum phải bị từ chối; không áp dụng tính chất về kết quả số cho các input nằm ngoài miền được chấp nhận.

Các tính chất nghiệp vụ:

~~~text
Tổng phần phân bổ = tổng đã chốt.
Dòng không đủ điều kiện không nhận tiền của thành phần đó.
Mỗi khoản ghi tiền truy được snapshot và phiên bản chính sách.
Tổng hoàn sau k đơn vị đúng bằng quyền lợi lũy kế đã quy định.
Hoàn đủ phần có thể hoàn đạt đúng tổng quyền hoàn cuối cùng.
Retry cùng lệnh không tạo thêm tác động tiền tệ.
Request sai quyền không làm thay đổi tiền hoặc tiêu thụ quyền lợi.
~~~

Giới hạn sai số `q/2` là tính chất của một phép làm tròn gần nhất, không phải mức dung sai cho việc đối chiếu expected của giao dịch. Nếu expected là `0.14`, không chấp nhận `0.15` bằng quy tắc “lệch một đơn vị nhỏ nhất vẫn được”.

### 11.3. Những tính chất không được giả định

Các mệnh đề sau không đúng tổng quát:

~~~text
R(a + b) = R(a) + R(b).
R(-x) = -R(x) với mọi mode.
Tách một nghiệp vụ thành nhiều nghiệp vụ luôn giữ nguyên tiền.
Làm tròn qua nhiều scale luôn giống làm tròn trực tiếp.
~~~

`CEILING` và `FLOOR` là phản ví dụ cho tính đối xứng dấu. Phí tính theo từng thanh toán là một lý do kết quả tách/gộp có thể khác theo chính sách.

Một property sai có thể ép cài đặt đúng phải đổi thành sai để test pass. Mỗi property cần nêu rõ mode, phạm vi kinh tế và điều kiện áp dụng.

### 11.4. Vector có phát hiện được những lỗi dự kiến không?

Có thể đánh giá chất lượng bộ dữ liệu bằng việc xét các thay đổi sai có chủ đích trong cài đặt kiểm thử:

| Thay đổi sai | Vector hoặc nhóm phải phát hiện |
|---|---|
| Đổi `HALF_UP` thành `HALF_EVEN` | P02 và M01 với expected khác nhau |
| Đổi `FLOOR` thành `DOWN` | M10, M14 trên số âm |
| Dùng `setScale(2)` thay cho quantum `0.05` | Q01–Q05 |
| Làm tròn đơn giá trước khi nhân | PIPE01 |
| Chuyển thuế tổng nhóm thành thuế theo dòng | PIPE02 |
| Làm tròn qua scale ba trước scale hai | PIPE05 |
| Bỏ phần dư phân bổ | AL01, AL02 |
| Phá hòa theo thứ tự request | Biến thể đảo đầu vào của AL01 |
| Hoàn độc lập từng request | RF01 và CC04 |
| Chỉ kiểm tra mã HTTP khi retry | ID01, ID04 cùng assert trạng thái bền vững |
| Bỏ phạm vi tenant hoặc quyền quote | SEC02, SEC03 |
| Cắt số bằng chuyển đổi không exact | IO03, IO05 |

Bảng này giúp chọn dữ liệu có sức phân biệt. Số lượng ca lớn không thay thế được khả năng bắt lỗi cụ thể.

## 12. Tổ chức bộ vector cho vòng đời của quy tắc nghiệp vụ

Một bộ vector có thể được nhóm theo:

~~~text
rounding-core
pricing-pipeline
allocation
refund-and-reversal
authorization-and-idempotency
concurrency-and-rollback
serialization-and-storage
historical-policy
~~~

Tên nhóm phục vụ việc quản lý, không bắt buộc phải tạo một cấu trúc thư mục cụ thể. Mỗi vector nên có ID ổn định để liên kết lỗi hoặc quyết định chính sách với một ca cụ thể.

Khi đưa một lỗi đã sửa vào bộ regression:

- Rút gọn thành fixture tổng hợp, không chứa thông tin khách hàng thật.
- Giữ đặc điểm tạo lỗi như nửa quantum, nhiều request hoặc phần dư.
- Ghi rõ expected về tiền và trạng thái sau xử lý.
- Xác định phiên bản chính sách mà vector bảo vệ.
- Giữ ca lịch sử nếu giao dịch cũ vẫn phải được hoàn hoặc đối soát theo quy tắc cũ.

Khi chính sách thay đổi, thêm expected cho phiên bản mới và quyết định rõ cách xử lý giao dịch đang chờ. Không chỉnh dữ liệu lịch sử để nó trông như đã được tạo theo chính sách mới.

Một bộ khởi đầu nên có ít nhất các ca trước/đúng/sau nửa quantum ở cả hai dấu, hai điểm nửa có kết quả `HALF_EVEN` khác nhau, một quantum `0.05`, một chuỗi tính giá có phần dư, một phân bổ có phá hòa, một chuỗi hoàn lũy kế, một retry sau commit và một tình huống đồng thời thực sự.

Để giải thích một kết quả kiểm thử, cần nêu được **đầu vào nào, chính sách nào, số tiền nào được kỳ vọng và trạng thái nào chứng minh không có tác động ngoài quyền**. Khi những yếu tố đó được ghi trong vector, bộ kiểm thử mới có thể phát hiện việc lạm dụng logic làm tròn ở cả phép tính và toàn bộ luồng tiền.
