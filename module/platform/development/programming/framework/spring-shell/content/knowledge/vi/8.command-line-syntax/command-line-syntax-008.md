# Giới hạn gộp tùy chọn ngắn theo từng phiên bản Spring Shell

Trong nhiều công cụ dòng lệnh, người dùng có thể viết `-abc` thay cho ba tùy chọn ngắn `-a -b -c`. Cách viết này thường được gọi là gộp tùy chọn ngắn (short-option grouping hoặc stacking). Tuy nhiên, parser của Spring Shell không giữ nguyên quy tắc đó qua mọi phiên bản: Spring Shell 3.x hỗ trợ gộp các tùy chọn ngắn kiểu boolean, còn Spring Shell 4.x không hỗ trợ gộp và yêu cầu mỗi option có giá trị tường minh, kể cả option boolean.

Khác biệt này ảnh hưởng trực tiếp đến command đã có trong script, tài liệu hướng dẫn và thói quen nhập lệnh của người dùng. Bài học này giải thích cách parser diễn giải cú pháp ở từng nhánh phiên bản, cách viết lệnh tương thích và cách kiểm thử khi nâng cấp.

## 1. Phân biệt option ngắn và gộp option ngắn

Option ngắn là tên tùy chọn gồm một ký tự, có dấu gạch ngang đơn ở trước. Ví dụ `-a`, `-b`, `-v`. Option dài thường có nhiều ký tự và dùng hai dấu gạch ngang, chẳng hạn `--all`, `--brief`, `--verbose`.

Ba cách viết sau có ý nghĩa khác nhau:

| Cú pháp | Ý nghĩa |
| --- | --- |
| `-a -b -c` | Ba option ngắn được viết tách biệt |
| `-abc` | Một chuỗi ngắn được gộp; cách diễn giải phụ thuộc phiên bản và kiểu option |
| `--all --brief --color` | Ba option dài được viết tách biệt |

Không nên mặc định rằng mọi parser CLI đều hỗ trợ `-abc`. Đây là quy tắc của parser cụ thể. Spring Shell 3.x và 4.x có hành vi khác nhau, vì vậy cần kiểm tra phiên bản Spring Shell thực tế mà ứng dụng đang sử dụng.

## 2. Hành vi gộp option ngắn trong Spring Shell 3.x

Tài liệu Spring Shell 3.4.1 mô tả short option có thể dùng dạng kết hợp. Nếu các option `a`, `b` và `c` đều được khai báo là cờ boolean, người dùng có thể viết `-abc` để bật cả ba.

Ví dụ theo annotation model của Spring Shell 3.x:

```java
@Component
public class InspectCommands {

    @Command(command = "inspect")
    public String inspect(
            @Option(shortNames = 'a') boolean all,
            @Option(shortNames = 'b') boolean brief,
            @Option(shortNames = 'c') boolean color) {

        return "all=" + all
                + ", brief=" + brief
                + ", color=" + color;
    }
}
```

Với ba option boolean đã khai báo, cách gọi:

```text
inspect -abc
```

có thể dùng dạng gộp tương đương ba cờ ngắn. Tài liệu 3.x cũng minh họa dạng `-abc true` và `-abc false` cho nhóm cờ boolean.

Gộp option phù hợp với các cờ boolean ngắn, độc lập và dễ nhớ. Không áp dụng máy móc cho option cần nhận một chuỗi hoặc số làm giá trị. Ví dụ `-o` có thể là option nhận đường dẫn file; khi đó hãy truyền giá trị theo cú pháp option có giá trị như `-o report.csv` hoặc `-o=report.csv`, thay vì gộp nó với các cờ khác.

Điểm quan trọng là phải khai báo từng short name trong command. Parser không thể suy ra ý nghĩa của `a`, `b` hoặc `c` nếu command không đăng ký các option tương ứng.

## 3. Spring Shell 4.x không hỗ trợ gộp short options

Spring Shell 4 thay đổi quy tắc phân tích dòng lệnh. Tài liệu 4.0.3 nêu rõ short option không thể được gộp; ví dụ `-abc` không được hỗ trợ như ba cờ `-a`, `-b`, `-c`.

Một short option trong Spring Shell 4 là một ký tự và có thể nhận giá trị theo một trong hai dạng:

```text
-k=value
-k value
```

Option dài có dạng:

```text
--key=value
--key value
```

Khác biệt quan trọng khác là khi một option xuất hiện, parser luôn mong đợi giá trị của option đó, kể cả khi kiểu Java là `boolean`. Vì vậy, không viết `-a` như một cờ bật độc lập theo thói quen từ 3.x. Hãy truyền `true` hoặc `false` rõ ràng.

Ví dụ annotation model Spring Shell 4.x:

```java
@Component
public class InspectCommands {

    @Command(name = "inspect")
    public String inspect(
            @Option(shortName = 'a') boolean all,
            @Option(shortName = 'b') boolean brief,
            @Option(shortName = 'c') boolean color) {

        return "all=" + all
                + ", brief=" + brief
                + ", color=" + color;
    }
}
```

Các cách gọi rõ ràng trong 4.x:

```text
inspect -a=true -b=true -c=true
inspect -a true -b true -c true
inspect --all=true --brief=true --color=true
```

Nếu muốn dùng giá trị mặc định `false`, có thể không truyền option tương ứng. Khi muốn bật hoặc tắt, truyền rõ giá trị boolean. `-abc` không phải cú pháp thay thế cho ba option boolean trong nhánh 4.x.

## 4. So sánh nhanh giữa hai phiên bản

| Nội dung | Spring Shell 3.x (ví dụ 3.4.1) | Spring Shell 4.x (ví dụ 4.0.3) |
| --- | --- | --- |
| Short name | Một ký tự, ví dụ `-a` | Một ký tự, ví dụ `-a` |
| Gộp nhiều short boolean options | Có, ví dụ `-abc` | Không hỗ trợ |
| Boolean option khi được truyền | Có thể dùng dạng cờ gộp theo quy tắc 3.x | Luôn phải có giá trị `true` hoặc `false` |
| Option có giá trị | Dùng short hoặc long option kèm giá trị | `-k=value`, `-k value`, `--key=value` hoặc `--key value` |
| Cách viết dễ chuyển phiên bản | Dùng option dài và giá trị tường minh | Dùng option dài và giá trị tường minh |

Đây là thay đổi của Spring Shell parser, không phải một quy tắc có thể suy ra chỉ từ tên hệ điều hành hoặc từ POSIX. Khi nâng phiên bản, hãy đọc cú pháp của đúng release thay vì dựa vào hành vi của một CLI khác.

## 5. Option boolean không đồng nghĩa với option không có giá trị

Một nhầm lẫn phổ biến là xem mọi option kiểu `boolean` như cờ chỉ cần xuất hiện là bật. Hành vi này phụ thuộc parser và cách option được khai báo.

Trong Spring Shell 3.x, tài liệu short format minh họa nhóm boolean options có thể gộp thành `-abc`. Đây là khả năng riêng được tài liệu mô tả cho short flags.

Trong Spring Shell 4.x, parser cần phân biệt giá trị option với positional argument, vì vậy mọi option được truyền vào đều cần một giá trị. Ví dụ:

```text
export --overwrite=true
export --overwrite false
export -o=true
export -o false
```

Nếu khai báo `defaultValue = "false"`, command có thể nhận `false` khi người dùng bỏ qua option. Khi người dùng truyền option, vẫn phải đưa giá trị tường minh theo quy tắc parser 4.x.

Với option boolean trong 4.x, nên viết `--overwrite=true` trong script để ý định rõ ràng và tránh nhầm giá trị option với positional argument kế tiếp.

## 6. Option ngắn có giá trị và option dài

Không phải option ngắn nào cũng là boolean. Một số option nhận chuỗi, số hoặc đường dẫn. Ví dụ `-o` nhận đường dẫn output, `-n` nhận số lượng bản ghi.

Các dạng sau thể hiện một option ngắn nhận một giá trị:

```text
report -o=summary.csv
report -o summary.csv
report --output=summary.csv
report --output summary.csv
```

Trong Spring Shell 4, cú pháp `-abc` không được dùng để gom ba option. Nếu muốn truyền ba giá trị khác nhau, hãy viết tách:

```text
search -a=active -b=before -c=created
```

hoặc dùng option dài dễ đọc hơn:

```text
search --status=active --sort=before --field=created
```

Không gán các short name dễ gây hiểu nhầm hoặc trùng lặp trong cùng command. Với command có nhiều tham số, tên dài thường giúp người dùng đọc lịch sử lệnh và script dễ hơn.

## 7. Viết cú pháp tương thích giữa 3.x và 4.x

Nếu ứng dụng cần hỗ trợ nhiều phiên bản Spring Shell hoặc có script được dùng qua giai đoạn nâng cấp, hãy chọn cú pháp chung an toàn. Cách đơn giản nhất là tránh gộp short options và dùng option dài kèm giá trị rõ ràng.

Ví dụ, thay vì:

```text
inspect -abc
```

hướng dẫn người dùng viết:

```text
inspect --all=true --brief=true --color=true
```

Hoặc nếu command sử dụng short aliases:

```text
inspect -a=true -b=true -c=true
```

Khi viết tài liệu, hãy ưu tiên cú pháp option dài vì ý nghĩa tự mô tả tốt hơn. Nếu dự án vẫn hỗ trợ Spring Shell 3.x và muốn giữ trải nghiệm gộp `-abc`, cần ghi rõ đó là cú pháp chỉ dùng cho phiên bản 3.x và cập nhật ví dụ khi chuyển sang 4.x.

Đừng cố dùng cùng một mã nguồn annotation cho cả hai nhánh nếu thuộc tính API đã đổi tên. Ví dụ annotation model 3.x dùng `shortNames` và `command`, trong khi Spring Shell 4 dùng `shortName` và `name`. Phần cần tương thích giữa phiên bản nên tập trung vào cú pháp người dùng nhập; phần khai báo Java vẫn cần theo API của dependency đang build.

## 8. Tùy biến parser trong Spring Shell 4

Spring Shell 4 cung cấp `CommandParser` để tùy biến quy tắc phân tích dòng lệnh. Nếu một sản phẩm có yêu cầu cú pháp riêng, có thể triển khai interface này và đăng ký implementation thành bean trong application context để Spring Shell dùng parser tùy chỉnh.

Chỉ nên tùy biến parser khi có yêu cầu rõ ràng, chẳng hạn cần tương thích với một cú pháp CLI cũ đã được công bố rộng rãi. Một parser riêng phải xử lý nhất quán:

- Tách tên command và subcommand.
- Nhận diện option dài, option ngắn và giá trị tương ứng.
- Xử lý boolean, positional arguments và chuỗi có dấu cách.
- Báo lỗi khi option không tồn tại, thiếu giá trị hoặc trùng lặp không hợp lệ.
- Không diễn giải nhầm giá trị option thành đối số vị trí.
- Giữ help, completion và command execution cùng hiểu một cú pháp.

Nếu tự hỗ trợ `-abc` trong parser 4.x, cần xác định chính xác từng ký tự có phải boolean flag hay không. Không nên coi mọi chuỗi bắt đầu bằng dấu gạch ngang đơn là một nhóm cờ, vì một short option có thể nhận một giá trị bắt đầu bằng chữ cái. Tài liệu và test phải ghi rõ quy tắc phân giải trường hợp mơ hồ.

## 9. Kiểm thử cú pháp khi nâng cấp

Kiểm thử parser ở cấp command giúp phát hiện khác biệt mà unit test của phương thức Java không thể thấy. Hãy chạy các lệnh qua shell test client của đúng phiên bản Spring Shell hoặc qua tiến trình JAR nếu cần kiểm tra hành vi cuối cùng.

Ma trận kiểm thử đề xuất:

| Trường hợp | Spring Shell 3.x | Spring Shell 4.x |
| --- | --- | --- |
| Ba boolean short options tách biệt | `-a -b -c` | `-a=true -b=true -c=true` |
| Ba boolean short options gộp | `-abc` được hỗ trợ theo tài liệu 3.x | Không hỗ trợ grouping |
| Boolean option có giá trị rõ ràng | Kiểm tra theo cách khai báo option | `-a=true` hoặc `--all=true` |
| Short option nhận chuỗi | `-o report.csv` | `-o report.csv` hoặc `-o=report.csv` |
| Long option nhận chuỗi | `--output report.csv` | `--output=report.csv` hoặc `--output report.csv` |
| Thiếu giá trị option | Xác nhận lỗi binding phù hợp | Xác nhận parser báo thiếu giá trị |
| Giá trị boolean sai định dạng | Xác nhận lỗi chuyển đổi | Xác nhận lỗi chuyển đổi |
| Positional argument đứng cạnh option | Kiểm tra đúng thứ tự bind | Kiểm tra đúng thứ tự bind |

Với script hiện có, tìm các lần gọi dạng `-abc`, `-xyz` hoặc những chuỗi short flags tương tự. Phân loại từng trường hợp: nhóm boolean, option có giá trị hay cú pháp không còn phù hợp. Sau đó chạy regression test với cả lệnh thành công và lệnh sai để xác nhận thông báo lỗi và exit code.

## 10. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `-abc` không chạy sau khi nâng lên 4.x | Spring Shell 4 không hỗ trợ nhóm short options | Tách thành `-a=true -b=true -c=true` |
| Boolean option báo thiếu giá trị | Parser 4.x yêu cầu mọi option có giá trị | Truyền `true` hoặc `false` rõ ràng |
| `-o=file` bị bind sai | Short name hoặc kiểu option khai báo không khớp | Kiểm tra `shortName` và kiểu dữ liệu; thử `-o file` |
| `-abc` được hiểu sai khi `a` nhận chuỗi | Nhầm nhóm flags với một option có giá trị | Không dùng cú pháp mơ hồ; viết `-a=bc` nếu thực sự muốn option `a` nhận chuỗi `bc` |
| Ví dụ tài liệu không biên dịch | Dùng annotation property của phiên bản khác | Kiểm tra `shortNames` ở 3.x và `shortName` ở 4.x |
| Script chạy được trên máy cũ nhưng lỗi trên CI | Máy dùng dependency Spring Shell khác nhau | Khóa version dependency và test trên artifact build thực tế |

Khi xử lý lỗi, xác định phiên bản dependency trước, sau đó xem cách khai báo option và cách gọi command. Không nên sửa parser trước khi xác nhận cú pháp người dùng thực sự cần.

## 11. Bài thực hành tổng hợp

Tạo command `inspect` có ba boolean options `all`, `brief` và `color`, mỗi option có short name `a`, `b`, `c` và long name tương ứng.

1. Trong nhánh Spring Shell 3.x, kiểm tra `inspect -abc` và xác nhận ba giá trị boolean được bật.
2. Thử `inspect -a -b -c` để quan sát cách viết tách biệt.
3. Trong nhánh Spring Shell 4.x, chạy `inspect -abc` và xác nhận cú pháp gộp không được hỗ trợ.
4. Thay bằng `inspect -a=true -b=true -c=true` và `inspect --all=true --brief=true --color=true`.
5. Thêm option `-o` / `--output` nhận đường dẫn file và kiểm tra các dạng `-o=report.csv` và `--output=report.csv`.
6. Viết integration test cho lệnh hợp lệ, lệnh gộp short options, boolean thiếu giá trị và option có giá trị.
7. Cập nhật README để ghi rõ cú pháp áp dụng cho phiên bản Spring Shell mà dự án đang dùng.

## 12. Tiêu chí hoàn thành

| Năng lực | Tiêu chí |
| --- | --- |
| Nhận diện cú pháp | Phân biệt option ngắn, option dài và nhóm short options |
| Spring Shell 3.x | Hiểu cách gộp các short boolean options như `-abc` |
| Spring Shell 4.x | Biết grouping không được hỗ trợ và option luôn cần giá trị |
| Boolean | Truyền `true`/`false` rõ ràng trong 4.x |
| Option có giá trị | Dùng đúng dạng `-k value`, `-k=value`, `--key value` hoặc `--key=value` |
| Tương thích | Chọn cú pháp chung rõ ràng cho script chạy qua nhiều phiên bản |
| Parser tùy chỉnh | Biết khi nào cần `CommandParser` và các trường hợp phải kiểm thử |
| Nâng cấp | Có regression test cho những lệnh cũ dùng short-option grouping |

## Tài liệu tham khảo

- [Spring Shell 3.4.1 — Short Format](https://docs.spring.io/spring-shell/reference/options/short.html)
- [Spring Shell 4.0.3 — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
