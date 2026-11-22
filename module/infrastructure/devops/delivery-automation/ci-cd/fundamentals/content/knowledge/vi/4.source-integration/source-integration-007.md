# Giữ nhánh chính hoạt động và thống nhất cách sửa build lỗi

Nhánh chính (`main`, hoặc tên nhánh mặc định tương đương) là điểm hội tụ của công việc phát triển. Mọi thay đổi đã tích hợp vào nhánh này đều có thể trở thành nền tảng cho pull request tiếp theo, cho lần tạo artifact kế tiếp và cho các môi trường kiểm thử hoặc phát hành. Vì vậy, nhóm cần giữ nhánh chính ở trạng thái có thể build và vượt qua các kiểm tra bắt buộc.

Một nhánh chính khỏe mạnh giúp nhóm trả lời nhanh ba câu hỏi: mã hiện tại có thể tích hợp không, thay đổi mới có làm hỏng điều gì không, và nhóm có thể tiếp tục phát triển trên cùng một nền tảng hay không. Để đạt được điều đó, nhóm cần kết hợp cách làm việc phù hợp với Git, chính sách bảo vệ nhánh, pipeline có phản hồi nhanh và một quy trình thống nhất khi build bị lỗi.

Trong phạm vi CI/CD, **giữ nhánh chính hoạt động** nghĩa là mỗi revision được chấp nhận vào nhánh chính phải vượt qua các kiểm tra chất lượng đã thống nhất, có kết quả gắn với commit cụ thể và không để lỗi chưa được xử lý kéo dài. Điều này không tự động chứng minh ứng dụng đã sẵn sàng đưa lên production; các cổng kiểm thử, bảo mật, phê duyệt và xác minh phát hành vẫn có thể cần thiết ở các bước sau.

## 1. Nhánh chính khỏe mạnh có ý nghĩa gì?

Nhánh chính khỏe mạnh là nhánh mà nhóm có thể dùng làm cơ sở chung để phát triển và tích hợp. Trạng thái này cần được định nghĩa bằng tiêu chí quan sát được, thay vì dựa vào cảm giác rằng “mọi thứ có vẻ ổn”.

Một bộ tiêu chí cơ bản thường gồm:

- Mã nguồn có thể checkout và build bằng quy trình được tài liệu hóa.
- Các kiểm tra bắt buộc như compile, unit test và những integration test quan trọng đều có kết quả đạt trên revision hiện tại.
- Pipeline được kích hoạt đúng, hoàn tất trong thời gian hợp lý và trả về trạng thái gắn với commit SHA.
- Artifact cần thiết có thể được tạo và nhận diện theo revision đã build.
- Các thay đổi chưa hoàn thiện có thể được tích hợp mà không làm lộ hành vi chưa sẵn sàng cho người dùng.
- Khi một kiểm tra bắt buộc thất bại, nhóm có chủ sở hữu và cách khôi phục rõ ràng.

“Luôn xanh” không có nghĩa là không bao giờ có lỗi. Lỗi vẫn có thể xuất hiện do regression, dependency, runner, registry hoặc dịch vụ kiểm thử. Điều quan trọng là lỗi được phát hiện tại cổng phù hợp, không bị bỏ qua và được xử lý đủ nhanh để nhánh chính sớm trở lại trạng thái tin cậy.

Nhóm cũng cần thống nhất định nghĩa của màu xanh. Ví dụ, nếu chỉ có compile và unit test chạy trên pull request, trạng thái xanh mới chứng minh được các điều kiện đó. Nó chưa chứng minh migration database, tích hợp dịch vụ bên ngoài hay hành vi sau triển khai hoạt động đúng. Tên gọi và phạm vi của mỗi cổng phải phản ánh đúng bằng chứng mà nó cung cấp.

## 2. Vì sao nên tích hợp thường xuyên?

Khi một nhánh tính năng tồn tại lâu, nó dần khác nhánh chính. Trong thời gian đó, các thành viên khác có thể đổi API, cập nhật dependency, sửa cấu trúc dữ liệu hoặc thay đổi pipeline. Đến lúc hợp nhất, nhóm phải giải quyết nhiều xung đột và có thể gặp những lỗi chỉ xuất hiện khi các thay đổi kết hợp với nhau.

Tích hợp thường xuyên giúp giảm kích thước của mỗi lần thay đổi và rút ngắn khoảng cách giữa nguyên nhân với kết quả. Khi một commit nhỏ làm build thất bại, phạm vi cần điều tra thường hẹp hơn so với một lần merge chứa hàng tuần thay đổi.

### Giữ nhánh làm việc ngắn hạn

Một cách tiếp cận phổ biến là phát triển theo trunk-based development: các nhánh tính năng có thời gian sống ngắn, thay đổi được chia thành phần nhỏ và tích hợp vào nhánh chính thường xuyên. Nhóm vẫn có thể dùng pull request để review, nhưng pull request nên đủ nhỏ để người khác hiểu, kiểm thử và phản hồi nhanh.

Quy trình có thể diễn ra như sau:

1. Tạo nhánh từ revision mới nhất của nhánh chính.
2. Thực hiện một thay đổi có mục đích rõ ràng, tránh gom nhiều việc độc lập vào cùng một pull request.
3. Chạy kiểm tra cần thiết tại máy phát triển và tạo pull request.
4. Pipeline kiểm tra revision của pull request; người review đánh giá cả mã nguồn lẫn ảnh hưởng tới tích hợp.
5. Khi các điều kiện bắt buộc đạt, merge thay đổi vào nhánh chính.
6. Pipeline trên nhánh chính xác minh revision sau merge và tạo artifact nếu cấu hình yêu cầu.

Nhóm không nhất thiết phải merge mọi commit chưa hoàn thiện ra nhánh chính. Thay vào đó, có thể chia một tính năng lớn thành các bước nhỏ nhưng vẫn giữ hành vi mới ở trạng thái tắt cho đến khi hoàn chỉnh.

### Dùng feature flag để tích hợp mã chưa bật tính năng

Feature flag cho phép mã mới được tích hợp và triển khai trong khi hành vi mới chưa được bật cho người dùng. Cách này hữu ích khi một tính năng cần nhiều pull request hoặc nhiều nhóm cùng làm.

Ví dụ đơn giản trong Java:

```java
public OrderView getOrder(String orderId) {
    Order order = orderRepository.findById(orderId);

    if (featureFlags.isEnabled("new-order-summary")) {
        return newOrderSummaryMapper.toView(order);
    }

    return legacyOrderSummaryMapper.toView(order);
}
```

Nhánh chính có thể chứa cả mapper mới và cờ điều khiển, trong khi người dùng vẫn nhận hành vi cũ cho đến khi nhóm bật tính năng. Flag cần có chủ sở hữu, mục đích và kế hoạch loại bỏ. Flag tồn tại quá lâu làm tăng số nhánh logic phải kiểm thử, khiến hành vi ứng dụng khó hiểu và có thể tạo ra những tổ hợp cấu hình không được xác minh.

Feature flag không thay thế kiểm thử. Dù một nhánh hành vi đang tắt, mã vẫn phải biên dịch và các đường đi liên quan cần được kiểm tra phù hợp. Với thay đổi về schema hoặc API, cần thiết kế tương thích ngược để phiên bản cũ và mới có thể cùng tồn tại trong giai đoạn chuyển tiếp.

## 3. Thiết lập quy tắc để bảo vệ nhánh chính

Chính sách bảo vệ nhánh biến kỳ vọng của nhóm thành điều kiện có thể thực thi. Nếu chỉ ghi trong tài liệu rằng “hãy chạy test trước khi merge”, kết quả vẫn phụ thuộc vào việc mỗi người có nhớ và thực hiện đầy đủ hay không.

Các quy tắc thường dùng gồm:

| Quy tắc | Mục đích | Lưu ý triển khai |
|---|---|---|
| Bắt buộc pull request | Mọi thay đổi đều đi qua review và kiểm tra | Giới hạn quyền push trực tiếp vào nhánh chính |
| Required status checks | Chỉ cho merge khi các job bắt buộc đạt | Chọn đúng check name và đúng workflow tạo kết quả |
| Review bắt buộc | Có người khác xem xét thay đổi | Quy định số lượng hoặc nhóm reviewer theo mức rủi ro |
| Giải quyết review conversation | Không để nhận xét chưa xử lý bị bỏ quên | Chỉ merge sau khi các trao đổi cần thiết đã được giải quyết |
| Kiểm tra cập nhật với nhánh đích | Xác minh thay đổi trên nền mã mới nhất | Có thể dùng merge queue khi nhiều pull request cạnh tranh |
| Giới hạn quyền quản trị và bypass | Bảo vệ tính nhất quán của cổng kiểm soát | Ngoại lệ cần người chịu trách nhiệm và được ghi nhận |

Không phải dự án nào cũng cần bật mọi quy tắc. Nhóm nên chọn theo mức độ rủi ro, quy mô và khả năng duy trì. Tuy nhiên, các kiểm tra quyết định khả năng build và chất lượng tích hợp phải được xác định rõ, có chủ sở hữu và được áp dụng nhất quán.

### Required status checks phải đại diện cho kiểm tra thực sự

Một status check chỉ hữu ích khi nó phản ánh một điều kiện cụ thể và chạy trên đúng revision cần merge. Nếu workflow bị bỏ qua do điều kiện trigger sai, check có thể ở trạng thái chờ mãi hoặc không cung cấp bằng chứng mà nhóm nghĩ rằng mình đang có.

Khi cấu hình, cần kiểm tra:

- Workflow có chạy với pull request từ các nhánh và loại thay đổi cần bảo vệ không?
- Check name có ổn định và không bị trùng giữa các job không?
- Kết quả có gắn với head SHA hoặc merge candidate tương ứng không?
- Job có thất bại đúng khi lệnh kiểm tra trả về lỗi không?
- Có bước nào dùng `continue-on-error` hoặc điều kiện bỏ qua khiến lỗi bị che khuất không?

Nếu một kiểm tra không còn phù hợp, hãy cập nhật chính sách và workflow cùng nhau. Không nên xóa check bắt buộc chỉ để giải quyết trạng thái chờ mà chưa hiểu nguyên nhân.

### Merge queue khi có nhiều thay đổi cùng lúc

Ở repository có nhiều pull request, hai thay đổi có thể đều xanh khi kiểm tra riêng nhưng không còn tương thích khi tích hợp cùng nhau. Merge queue tạo một ứng viên tích hợp theo thứ tự và chạy lại các kiểm tra trên trạng thái kết hợp trước khi đưa thay đổi vào nhánh đích.

Merge queue hữu ích khi nhánh chính thường xuyên nhận nhiều pull request hoặc khi thời gian chạy kiểm tra đủ dài khiến nhiều pull request cùng dựa trên một trạng thái cũ. Queue làm tăng một phần thời gian chờ, nhưng giúp giảm nguy cơ hai thay đổi độc lập cùng vượt qua kiểm tra riêng rồi làm hỏng nhánh chính khi được merge gần nhau.

Để queue hoạt động đúng, workflow phải hỗ trợ sự kiện và revision mà nền tảng dùng cho merge group hoặc merge train. Nếu workflow chỉ chạy cho `pull_request` và `push` mà không hỗ trợ sự kiện cần thiết, queue có thể không nhận được check bắt buộc.

## 4. Giữ chất lượng tích hợp mà không làm chậm nhóm

Nhánh chính khỏe mạnh phụ thuộc vào chất lượng của phản hồi CI. Nếu một thay đổi phải chờ quá lâu, nhóm có xu hướng tìm cách bỏ qua kiểm tra hoặc merge nhiều thay đổi cùng lúc. Nếu kiểm tra không ổn định, người phát triển sẽ dần mất niềm tin vào trạng thái xanh và đỏ.

### Phân lớp kiểm tra

Nhóm nên tổ chức các kiểm tra theo thời gian và mức độ rủi ro:

- Kiểm tra cú pháp, format, lint và biên dịch thường chạy sớm.
- Unit test chạy trong mỗi pull request và trên nhánh chính.
- Integration test quan trọng chạy trước khi merge hoặc trên merge candidate.
- Các bộ kiểm thử tốn thời gian như hiệu năng, khả năng chịu tải hoặc kiểm thử trên nhiều nền tảng có thể chạy theo lịch hay trước một cổng phát hành phù hợp.

Việc phân lớp phải được thống nhất với nhóm sản phẩm và kỹ thuật. Một kiểm tra chỉ được chuyển khỏi cổng merge khi đã đánh giá rủi ro và xác định điểm kiểm soát thay thế. Không nên đẩy kiểm tra quan trọng sang sau merge chỉ để làm hàng chờ pull request ngắn hơn.

### Tối ưu thời gian CI

Các cách thường dùng để giảm thời gian phản hồi gồm cache dependency, chỉ chạy job liên quan khi có thay đổi phù hợp, chia test thành các nhóm độc lập và chạy song song trên runner đủ tài nguyên. Cần đo riêng thời gian chờ runner, thời gian setup và thời gian thực thi để biết phần nào đang làm pipeline chậm.

Cache phải được thiết kế theo hệ điều hành, phiên bản runtime, lockfile hoặc các yếu tố ảnh hưởng đến dependency. Cache sai có thể đưa file cũ vào build và tạo lỗi khó tái hiện. Khi build phụ thuộc vào cache, nhóm vẫn phải có cách chạy sạch để chẩn đoán.

### Kiểm thử không ổn định

Test flaky là test có thể đạt hoặc thất bại dù mã nguồn và điều kiện đầu vào không đổi. Nguyên nhân thường đến từ chia sẻ dữ liệu, phụ thuộc thứ tự, race condition, thời gian, mạng hoặc dịch vụ bên ngoài.

Khi phát hiện test flaky:

1. Ghi nhận test, revision, môi trường và log của các lần chạy đạt hoặc thất bại.
2. Thử tái hiện nhiều lần trong điều kiện có kiểm soát.
3. Tách nguyên nhân do test, do ứng dụng hay do môi trường.
4. Sửa test để cô lập dữ liệu, kiểm soát thời gian hoặc loại bỏ phụ thuộc không cần thiết.
5. Chạy lại đủ số lần phù hợp và đưa test trở lại cổng bắt buộc nếu trước đó đã cách ly.

Retry có giới hạn có thể giúp xử lý một lỗi hạ tầng thoáng qua, nhưng trạng thái cuối cùng phải giữ được bằng chứng về lần thất bại. Không dùng retry vô hạn hoặc tự động bỏ qua test để tạo ra một kết quả xanh không phản ánh chất lượng thật.

## 5. Thống nhất quy trình xử lý khi build trên nhánh chính bị lỗi

Khi build trên nhánh chính thất bại, cả nhóm cần phản ứng theo cùng một quy trình. Quy trình chuẩn giảm thời gian tranh luận, tránh nhiều người sửa cùng một chỗ và giúp giữ lại bằng chứng để xác định nguyên nhân.

### Nguyên tắc phản ứng

- **Một lỗi chặn luồng cần một chủ sở hữu điều phối.** Có thể có nhiều người hỗ trợ, nhưng phải rõ ai đang dẫn dắt việc khôi phục.
- **Tạm dừng đưa thêm thay đổi có rủi ro vào nhánh đang hỏng.** Việc tạm dừng nên giới hạn ở repository hoặc luồng bị ảnh hưởng; các công việc độc lập có thể tiếp tục nếu không làm khó quá trình khôi phục.
- **Sửa nguyên nhân gốc hoặc revert thay đổi gây lỗi.** Không làm xanh pipeline bằng cách xóa test hay bỏ qua cổng bắt buộc.
- **Xác minh lại trên revision mới.** Một lần chạy xanh trên commit cũ không chứng minh commit sau sửa đã an toàn.
- **Thông báo trạng thái rõ ràng.** Mọi người cần biết lỗi đang được xử lý, ai phụ trách và khi nào có cập nhật tiếp theo.

### Quy trình năm bước

#### Bước 1: Công bố build đỏ và xác định phạm vi

Khi pipeline của nhánh chính thất bại, người phát hiện thông báo ngay vào kênh hoặc công cụ theo dõi sự cố của nhóm. Thông tin ban đầu nên có liên kết tới workflow run, nhánh, commit SHA, job lỗi và thời điểm phát hiện.

Xác định lỗi có thực sự ảnh hưởng tới nhánh chính hay chỉ là một pull request riêng lẻ. Kiểm tra xem job nào thất bại đầu tiên, job nào chỉ bị skipped do phụ thuộc và liệu có nhiều lần chạy cùng báo một lỗi hay không.

#### Bước 2: Chọn chủ sở hữu và hạn chế thay đổi mới

Người điều phối có thể là tác giả commit gây lỗi, người trực build hoặc người phụ trách repository theo quy ước nhóm. Nếu chưa rõ nguyên nhân, người trực build điều phối việc thu thập bằng chứng và gọi đúng nhóm chuyên môn vào hỗ trợ.

Trong thời gian mainline đỏ, nhóm nên hạn chế merge thêm thay đổi không khẩn cấp. Nếu có một thay đổi cần thiết để khắc phục sự cố production, hãy đánh giá riêng và ghi nhận quyết định. Tránh để nhiều commit không liên quan tiếp tục đi vào nhánh vì chúng làm tăng số giả thuyết cần kiểm tra.

#### Bước 3: Tìm lỗi đầu tiên và tái hiện

Mở log của job thất bại đầu tiên, xác định lệnh trả về mã lỗi và xem phần log ngay trước đó. So sánh revision lỗi với lần chạy xanh gần nhất để khoanh vùng thay đổi. Kiểm tra cả dependency, cấu hình, secret, runner và dịch vụ kiểm thử nếu dấu hiệu cho thấy lỗi không nằm trong mã ứng dụng.

Với dự án Gradle, có thể bắt đầu từ các lệnh sau trong một working tree phù hợp:

```bash
# Xem trạng thái và commit hiện tại
git status --short
git log --oneline -n 10

# Chạy lại các kiểm tra chính
./gradlew --no-daemon clean check

# Chạy riêng một nhóm test khi đã xác định được module
./gradlew :order-service:test
```

Tên task và module cần điều chỉnh theo dự án. Lệnh `clean` giúp loại bỏ một số đầu ra build cũ, nhưng không tái tạo được mọi khác biệt về runner, biến môi trường hoặc dịch vụ bên ngoài. Nếu lỗi chỉ xuất hiện trên CI, cần so sánh phiên bản JDK, Gradle, hệ điều hành, biến cấu hình và dependency giữa môi trường CI với máy phát triển.

#### Bước 4: Sửa lỗi hoặc revert

Chọn cách khôi phục dựa trên độ chắc chắn của nguyên nhân và thời gian cần thiết:

| Trường hợp | Cách xử lý thường phù hợp |
|---|---|
| Một commit vừa merge gây lỗi rõ ràng, bản sửa cần nhiều thời gian | Revert commit gây lỗi để khôi phục mainline, sau đó sửa trên nhánh riêng |
| Nguyên nhân đã rõ và bản sửa nhỏ, có thể kiểm thử đầy đủ | Tạo pull request sửa lỗi khẩn cấp, review tập trung và chạy cổng bắt buộc |
| Runner, registry hoặc dịch vụ kiểm thử bị gián đoạn | Khôi phục dịch vụ hoặc cấu hình, sau đó chạy lại đúng revision |
| Test flaky làm pipeline đỏ | Xác minh tính không ổn định, sửa test hoặc cách ly có kiểm soát với thời hạn rõ ràng |
| Nhiều commit có thể gây lỗi và chưa xác định được nguyên nhân | Giới hạn merge mới, điều tra theo revision và dùng công cụ như `git bisect` khi phù hợp |

`git revert` tạo một commit mới đảo ngược thay đổi đã có trong lịch sử, phù hợp với nhánh dùng chung. Không tùy tiện viết lại lịch sử nhánh chính bằng reset hoặc force push vì việc đó có thể làm mất commit và gây lệch lịch sử của các thành viên khác. Nếu cần xử lý lịch sử đặc biệt, phải theo quy trình quản trị repository của nhóm.

#### Bước 5: Xác minh, mở lại luồng và ghi nhận

Sau khi sửa hoặc revert, chạy lại toàn bộ status check bắt buộc trên revision mới. Xác nhận build, test, artifact và các job phụ thuộc đã hoàn tất. Nếu đã tạm dừng merge, người điều phối thông báo khi nhánh chính trở lại trạng thái đạt và nhóm có thể tiếp tục tích hợp.

Ghi nhận nguyên nhân gốc, cách phát hiện, thời gian ảnh hưởng, hành động khôi phục và biện pháp ngăn tái diễn. Nếu sự cố được xử lý bằng workaround, tạo công việc theo dõi để hoàn tất bản sửa và khôi phục những kiểm tra đã tạm thời thay đổi.

## 6. Phân vai để tránh xử lý chồng chéo

Ở nhóm nhỏ, một người có thể đảm nhiệm nhiều vai trò. Dù vậy, trách nhiệm cần rõ ràng để mọi người biết ai đang điều phối và ai quyết định mở lại luồng tích hợp.

| Vai trò | Trách nhiệm chính |
|---|---|
| Tác giả thay đổi | Cung cấp bối cảnh, commit liên quan, cách tái hiện và hỗ trợ sửa lỗi do thay đổi của mình |
| Người trực build hoặc điều phối | Phát hiện build đỏ, công bố trạng thái, xác định chủ sở hữu, theo dõi thời gian khôi phục và xác nhận luồng đã xanh |
| Người review | Kiểm tra bản sửa khẩn cấp, đánh giá rủi ro và xác nhận thay đổi không làm suy yếu cổng chất lượng |
| Chủ sở hữu dịch vụ hoặc nền tảng | Điều tra runner, registry, dependency, môi trường và dịch vụ tích hợp dùng chung |
| Người phụ trách repository | Duy trì branch protection, required checks và quyền ngoại lệ |

Một số nhóm luân phiên vai trò **build sheriff** hoặc **build cop** theo ngày hay theo tuần. Người trực không phải tự sửa mọi lỗi; nhiệm vụ chính là giữ cho lỗi có người phụ trách, có thông tin và được xử lý tới khi đóng. Cách luân phiên giúp phân tán kiến thức về pipeline và giảm phụ thuộc vào một cá nhân.

## 7. Mẫu thông báo khi build bị hỏng

Thông báo sự cố nên ngắn gọn, có thể hành động và được cập nhật khi trạng thái thay đổi. Một mẫu dùng trong kênh nhóm:

```text
[MAIN BUILD BROKEN]
Repository: <repository>
Branch: main
Commit: <commit-sha>
Workflow run: <link>
Failing job/step: <job-and-step>
Impact: <merge-blocked / artifact-unavailable / other>
Owner: <person-or-team>
Current action: <investigating / reverting / fixing>
Next update: <time-or-condition>
```

Khi khôi phục xong, gửi thông báo đóng sự cố:

```text
[MAIN BUILD RESTORED]
Repository: <repository>
Verified commit: <commit-sha>
Workflow run: <link>
Required checks: <passed-checks>
Recovery: <fix-or-revert>
Follow-up: <issue-or-none>
```

Không đưa token, mật khẩu, nội dung secret hoặc dữ liệu nhạy cảm vào thông báo và log. Nếu cần chia sẻ log, dùng liên kết có quyền truy cập phù hợp và kiểm tra rằng log không chứa thông tin xác thực.

## 8. Ví dụ workflow kiểm tra trước khi merge

Ví dụ GitHub Actions dưới đây minh họa một job kiểm tra cho dự án Gradle. Kết quả của job có thể được dùng làm required status check trong chính sách bảo vệ nhánh.

```yaml
name: Mainline verification

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

permissions:
  contents: read

concurrency:
  group: verify-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  verify:
    name: verify
    runs-on: ubuntu-latest
    timeout-minutes: 25
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - name: Set up Gradle
        uses: gradle/actions/setup-gradle@v4

      - name: Run required checks
        run: ./gradlew --no-daemon clean check
```

Job `verify` được đặt tên rõ để nhóm chọn đúng check trong branch protection. `pull_request` kiểm tra thay đổi trước khi merge; `push` vào `main` xác minh trạng thái sau tích hợp. `timeout-minutes` ngăn một lần chạy treo vô hạn.

Phần `concurrency` là ví dụ cần cân nhắc trước khi dùng. Với cùng một ref, lần chạy mới có thể hủy lần chạy đang chạy. Điều này phù hợp với một số workflow kiểm tra trạng thái mới nhất, nhưng không phù hợp với job tạo artifact cần lưu giữ, job triển khai hoặc công việc không thể bị hủy an toàn. Khi áp dụng, cần kiểm tra cách nền tảng xử lý pull request, merge queue và các lần chạy cần hoàn tất độc lập.

Ví dụ cũng chưa bao gồm integration test, scan bảo mật, xuất báo cáo coverage hoặc upload artifact. Nhóm cần thêm các điều kiện thực tế vào job và cấu hình đúng required checks. Nếu dùng merge queue, hãy bổ sung trigger và kiểm tra tương thích với merge group theo nền tảng đang sử dụng.

## 9. Những lỗi quy trình thường làm nhánh chính mất ổn định

| Thói quen | Hệ quả | Cách cải thiện |
|---|---|---|
| Nhánh tính năng sống quá lâu | Tích lũy xung đột và sai khác với main | Chia thay đổi nhỏ, tích hợp thường xuyên |
| Merge khi required check chưa đạt | Lỗi đi thẳng vào nhánh chính | Bật branch protection và kiểm tra check thực sự bắt buộc |
| Chỉ kiểm tra pull request, không xác minh sau merge | Bỏ sót lỗi do tích hợp hoặc cấu hình nhánh chính | Chạy pipeline trên push vào main hoặc merge candidate |
| Nhiều người sửa build cùng lúc mà không điều phối | Xung đột bản sửa, mất dấu nguyên nhân | Chỉ định một người điều phối và phân công rõ |
| Tắt test để build xanh | Mất khả năng phát hiện regression | Sửa test hoặc cách ly có thời hạn và biện pháp thay thế |
| Re-run nhiều lần mà không điều tra | Che khuất test flaky hoặc lỗi môi trường | Giữ log, phân loại và tái hiện có kiểm soát |
| Không ghi lại quyết định revert hoặc bypass | Khó truy vết và dễ lặp lại sai sót | Ghi lý do, người quyết định và bước theo dõi |
| Không có người trực hoặc kênh thông báo | Build đỏ kéo dài mà không ai nhận trách nhiệm | Thiết lập ownership và quy tắc thông báo |

Đặc biệt, không nên xem “build xanh” là mục tiêu độc lập. Nếu nhóm đạt trạng thái xanh bằng cách bỏ kiểm tra, giảm ngưỡng chất lượng tùy tiện hoặc che giấu kết quả thất bại, nhánh chính sẽ mất độ tin cậy. Mỗi thay đổi đối với cổng chất lượng phải có lý do, người sở hữu và kế hoạch xác minh.

## 10. Đo lường sức khỏe của nhánh chính

Nhóm có thể theo dõi một số chỉ số để biết quy trình có thực sự giữ được mainline ổn định hay không:

| Chỉ số | Cách hiểu | Dấu hiệu cần xem xét |
|---|---|---|
| Tỷ lệ thời gian mainline xanh | Phần thời gian nhánh chính vượt qua các kiểm tra bắt buộc | Giảm kéo dài cho thấy lỗi tích hợp hoặc môi trường chưa được xử lý tốt |
| Thời gian khôi phục build | Thời gian từ lúc build chính bị hỏng đến lúc kiểm tra bắt buộc đạt trở lại | Tăng cao có thể do thiếu ownership, log hoặc quy trình revert |
| Số lần build chính bị hỏng | Tần suất regression hoặc sự cố pipeline | Phân loại theo nguyên nhân để tìm nhóm lỗi lặp lại |
| Thời gian chờ pull request | Thời gian từ khi mở pull request đến khi đủ điều kiện merge | Tách thời gian chờ review, runner và sửa lỗi để tối ưu đúng điểm |
| Tỷ lệ test flaky | Mức độ ổn định của các kiểm tra | Tăng cao làm giảm niềm tin vào required checks |
| Số lần bypass cổng chất lượng | Mức độ sử dụng ngoại lệ | Ngoại lệ lặp lại có thể cho thấy chính sách hoặc năng lực kiểm tra chưa phù hợp |

Định nghĩa cách tính nhất quán. Ví dụ, thời gian khôi phục build có thể bắt đầu từ lần chạy đầu tiên xác nhận mainline thất bại và kết thúc ở lần chạy thành công trên revision đã sửa hoặc revert. Cần phân biệt thời gian sự cố với thời gian chờ cập nhật trạng thái nếu muốn tìm đúng nút thắt.

Không dùng một chỉ số đơn lẻ để đánh giá hiệu quả. Tỷ lệ mainline xanh cao nhưng thời gian chờ pull request quá dài có thể cho thấy nhóm đang kiểm tra quá nhiều thứ ở một điểm. Thời gian khôi phục ngắn nhưng số lần bypass tăng có thể cho thấy nhóm đang ưu tiên trạng thái xanh hơn chất lượng. Hãy đọc các chỉ số cùng bối cảnh, xu hướng và phản hồi của người phát triển.

## 11. Checklist giữ nhánh chính hoạt động

Khi thiết lập hoặc rà soát repository, nhóm có thể dùng checklist sau:

- [ ] Có định nghĩa rõ ràng về trạng thái mainline xanh và các kiểm tra bắt buộc.
- [ ] Nhánh chính được bảo vệ; quyền push trực tiếp và quyền bypass được giới hạn.
- [ ] Pull request có kích thước phù hợp, có review và có liên kết tới thay đổi liên quan.
- [ ] Nhánh tính năng được tích hợp thường xuyên; thay đổi chưa hoàn thiện dùng feature flag khi phù hợp.
- [ ] Pipeline kiểm tra đúng revision trước merge và xác minh lại sau tích hợp.
- [ ] Required status checks có tên ổn định, chạy đúng trigger và không che giấu lỗi.
- [ ] Merge queue được cân nhắc khi nhiều pull request thường xuyên cạnh tranh cùng nhánh.
- [ ] Test flaky có quy trình điều tra, chủ sở hữu và thời hạn khắc phục.
- [ ] Khi mainline đỏ, nhóm có người điều phối, kênh thông báo và quy trình fix hoặc revert thống nhất.
- [ ] Bản sửa được xác minh trên commit mới trước khi mở lại luồng merge.
- [ ] Ngoại lệ và workaround được ghi nhận, có thời hạn và có việc theo dõi.
- [ ] Nhóm theo dõi thời gian mainline bị hỏng, thời gian chờ pull request và tỷ lệ test flaky.

Giữ nhánh chính hoạt động là kỷ luật chung của cả nhóm. Các thay đổi nhỏ, tích hợp thường xuyên, cổng kiểm tra có ý nghĩa và quy trình xử lý build đỏ nhất quán giúp mọi người luôn làm việc trên một nền mã đáng tin cậy. Khi build gặp lỗi, nhóm cần nhanh chóng xác định chủ sở hữu, khôi phục bằng cách có thể kiểm chứng và chỉ tiếp tục tích hợp khi revision mới đã vượt qua các điều kiện bắt buộc.
