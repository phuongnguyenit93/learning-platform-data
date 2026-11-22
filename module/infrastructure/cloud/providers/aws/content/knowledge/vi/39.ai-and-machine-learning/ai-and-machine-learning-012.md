# Transcribe, Translate, Polly và tích hợp xử lý ngôn ngữ

Amazon Transcribe, Amazon Translate và Amazon Polly giải quyết ba bước khác nhau trong ứng dụng xử lý ngôn ngữ:

- **Amazon Transcribe:** chuyển giọng nói thành văn bản (speech-to-text).
- **Amazon Translate:** dịch văn bản giữa ngôn ngữ nguồn và ngôn ngữ đích (machine translation).
- **Amazon Polly:** chuyển văn bản thành giọng nói (text-to-speech).

Kết hợp ba dịch vụ giúp xây dựng phụ đề, biên bản cuộc họp, tổng đài đa ngôn ngữ, nội dung học tập, ứng dụng trợ năng và hệ thống phát nội dung bằng giọng nói. Tuy nhiên, không phải mọi ngôn ngữ đều được cả ba dịch vụ hỗ trợ như nhau. Đặc biệt, tiếng Việt được Transcribe nhận dạng và Translate dịch, nhưng hiện không nằm trong danh sách ngôn ngữ/giọng đọc được Polly hỗ trợ. Thiết kế pipeline phải kiểm tra khả năng của từng dịch vụ theo ngôn ngữ, tính năng và Region trước khi triển khai.

Bài học thuộc chương **AI và machine learning** trong module CLOUD_PROVIDERS_AWS. Module giúp người học khám phá hệ sinh thái AWS từ Region/AZ, IAM, VPC đến compute, storage, database, integration và serverless; qua đó rèn khả năng chọn dịch vụ, thiết kế và triển khai ứng dụng an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt speech-to-text, machine translation và text-to-speech.
- Chọn batch transcription hay streaming transcription trong Amazon Transcribe.
- Cấu hình ngôn ngữ, channel identification, speaker diarization, custom vocabulary và vocabulary filtering theo khả năng hỗ trợ.
- Dùng Amazon Translate cho real-time text, document translation và batch translation.
- Áp dụng custom terminology, parallel data và các tùy chọn điều chỉnh bản dịch.
- Chọn engine, voice, output format, SSML, lexicon và speech marks trong Amazon Polly.
- Thiết kế pipeline xử lý âm thanh và văn bản với S3, EventBridge, Step Functions, Lambda, SQS, SNS và DynamoDB.
- Tích hợp bằng AWS SDK for Java 2.x và AWS CLI.
- Bảo vệ audio, transcript, bản dịch và audio output bằng IAM, KMS, S3 policy, retention và kiểm soát dữ liệu nhạy cảm.
- Đo chất lượng, độ trễ, độ tin cậy và chi phí của pipeline.

## 1. Bức tranh tổng thể: ba dịch vụ, ba nhiệm vụ

| Dịch vụ | Đầu vào | Đầu ra | Bài toán tiêu biểu |
|---|---|---|---|
| Amazon Transcribe | Audio/video có âm thanh hoặc luồng audio | Transcript, timestamp, confidence, speaker/channel metadata tùy cấu hình | Phụ đề, ghi biên bản, tìm kiếm trong bản ghi, phân tích cuộc gọi |
| Amazon Translate | Văn bản hoặc tài liệu | Văn bản/tài liệu đã dịch | Ứng dụng đa ngôn ngữ, dịch email, nội dung website, tài liệu |
| Amazon Polly | Văn bản hoặc SSML | Audio tổng hợp, speech marks trong request riêng | Đọc nội dung, voice prompt, narration, trợ năng |

~~~mermaid
flowchart LR
    A[Audio đầu vào] --> B[Amazon Transcribe]
    B --> C[Transcript nguồn]
    C --> D[Amazon Translate]
    D --> E[Văn bản ngôn ngữ đích]
    E --> F[Amazon Polly]
    F --> G[Audio đầu ra]
    C --> H[S3 / Search / Analytics]
    E --> H
    G --> I[Ứng dụng / CDN]
~~~

Mỗi bước có latency, giới hạn, ngôn ngữ, quyền IAM và chi phí riêng. Nếu đầu vào là tiếng Việt, Transcribe có thể tạo transcript `vi-VN`, Translate có thể dịch với mã ngôn ngữ `vi`; Polly cần một ngôn ngữ và voice có trong danh sách hỗ trợ. Nếu sản phẩm cần phát lại bằng tiếng Việt, phải chọn một giải pháp TTS khác cho bước cuối.

## 2. Kiểm tra hỗ trợ ngôn ngữ trước khi thiết kế

Đây là bước bắt buộc khi xây dựng ứng dụng đa ngôn ngữ. Danh sách ngôn ngữ cơ bản không đồng nghĩa mọi tính năng đều có cho ngôn ngữ đó.

### 2.1. Tiếng Việt trên ba dịch vụ

| Khả năng | Amazon Transcribe | Amazon Translate | Amazon Polly |
|---|---|---|---|
| Ngôn ngữ | Vietnamese `vi-VN` | Vietnamese `vi` | Không có trong danh sách ngôn ngữ hỗ trợ hiện hành |
| Batch | Có | Có | Có cho văn bản thuộc ngôn ngữ/voice hỗ trợ |
| Real-time/streaming | Streaming transcription có hỗ trợ | Real-time text translation có hỗ trợ | Không có voice tiếng Việt để tổng hợp |
| Một số giới hạn tính năng | Không có PII redaction, custom language model và Call Analytics cho `vi-VN` trong bảng feature support hiện hành | Profanity masking không hỗ trợ tiếng Việt; brevity chỉ dành cho real-time text translation | Cần chuyển văn bản sang ngôn ngữ có voice hỗ trợ hoặc dùng TTS khác |

Điểm cần ghi nhớ:

- Transcribe hỗ trợ batch và streaming cho `vi-VN`. Bảng ngôn ngữ hiện hành cũng liệt kê number normalization cho batch và acronym handling cho batch/streaming.
- Transcribe không hỗ trợ PII redaction cho `vi-VN`. Không được coi transcript tiếng Việt đã tự động loại bỏ tên, số điện thoại, địa chỉ hoặc thông tin tài khoản.
- Amazon Translate hỗ trợ tiếng Việt với language code `vi`. Tính năng mở rộng như formality, brevity, profanity masking và parallel data có ma trận hỗ trợ riêng.
- Amazon Translate không áp dụng profanity masking cho tiếng Việt. Nếu nội dung cần kiểm duyệt, phải xây dựng lớp kiểm tra phù hợp và có người đánh giá khi cần.
- Danh sách voice của Polly hiện không có Vietnamese. Không gửi văn bản tiếng Việt vào Polly rồi kỳ vọng có giọng đọc tiếng Việt.

Danh sách hỗ trợ có thể thay đổi theo thời gian. Trước khi phát hành, kiểm tra trang supported languages, feature matrix, voice catalog và Region compatibility của từng dịch vụ.

### 2.2. Language code không giống nhau giữa các dịch vụ

| Dịch vụ | Ví dụ mã tiếng Việt | Cách dùng |
|---|---|---|
| Transcribe | `vi-VN` | `LanguageCode` |
| Translate | `vi` | `SourceLanguageCode` hoặc `TargetLanguageCode` |
| Polly | Không có mã tiếng Việt hiện hành | Chọn voice ID thuộc ngôn ngữ hỗ trợ |

Không truyền `vi-VN` vào Translate hoặc `vi` vào Transcribe. Mỗi API dùng quy ước language code riêng.

## 3. Amazon Transcribe: speech-to-text

Amazon Transcribe là dịch vụ nhận dạng giọng nói tự động (Automatic Speech Recognition — ASR). Dịch vụ phân tích audio và trả transcript cùng metadata để ứng dụng có thể hiển thị, tìm kiếm hoặc xử lý tiếp.

### 3.1. Batch transcription và streaming transcription

| Tiêu chí | Batch transcription | Streaming transcription |
|---|---|---|
| Đầu vào | Media file trong Amazon S3 | Audio được gửi liên tục qua HTTP/2 hoặc WebSocket |
| Kết quả | Job bất đồng bộ; kết quả được lưu thành transcript | Partial và final result được gửi trong lúc stream |
| Phù hợp | Cuộc họp đã ghi, podcast, video, file tổng đài | Phụ đề trực tiếp, voice interface, tổng đài realtime |
| Điều phối | Start job, theo dõi trạng thái, xử lý kết quả | Giữ kết nối stream và quản lý vòng đời session |
| Đặc điểm | Dễ retry/replay theo file | Nhạy với network, audio format và latency |

**Batch** phù hợp khi có file hoàn chỉnh và không cần transcript ngay lập tức. Ứng dụng đưa media vào S3, gọi `StartTranscriptionJob`, theo dõi trạng thái `QUEUED`, `IN_PROGRESS`, `COMPLETED` hoặc `FAILED`, rồi lấy transcript khi job kết thúc.

**Streaming** phù hợp khi cần hiển thị kết quả trong lúc người dùng nói. Ứng dụng mở stream, gửi các audio chunk và nhận transcript event. Streaming sử dụng HTTP/2 hoặc WebSocket; AWS CLI không hỗ trợ streaming transcription, cần SDK hoặc giao thức streaming phù hợp.

### 3.2. Định dạng và chất lượng audio

Chất lượng transcript phụ thuộc lớn vào chất lượng audio đầu vào:

- Chọn media encoding và sample rate đúng với audio thực tế.
- Tránh khai báo sample rate khác với dữ liệu đã gửi.
- Giảm tiếng ồn, clipping, echo và âm thanh nền.
- Dùng microphone phù hợp và giữ âm lượng tương đối ổn định.
- Với audio nhiều người nói, cân nhắc tách channel từ thiết bị ghi âm.
- Không resample lên tần số cao hơn rồi kỳ vọng khôi phục thông tin đã mất.

Với streaming, request cần có `LanguageCode` hoặc cấu hình language identification, `MediaEncoding` và `MediaSampleRateHertz`. Audio PCM thường dùng PCM signed 16-bit little-endian; sample rate phải khớp luồng audio. Chọn codec và sample rate theo hướng dẫn của Transcribe và khả năng thiết bị.

### 3.3. Chọn ngôn ngữ hay tự nhận diện?

Nếu biết trước ngôn ngữ, chỉ định language code cụ thể thường là lựa chọn dễ kiểm soát hơn.

- Batch có thể dùng `LanguageCode` để chỉ định ngôn ngữ.
- Khi không biết ngôn ngữ, có thể dùng language identification với danh sách ngôn ngữ ứng viên.
- Multi-language identification phù hợp khi media có nhiều ngôn ngữ được nói.
- Với streaming, language identification yêu cầu khai báo `LanguageOptions`; có thể thêm `PreferredLanguage` nếu đã có dự đoán ban đầu.
- Để nhận dạng tiếng Việt, dùng `vi-VN` khi biết audio là tiếng Việt.

Không đưa một danh sách ngôn ngữ ứng viên quá rộng nếu có thể giới hạn bằng metadata của ứng dụng. Điều này giúp giảm mơ hồ khi audio ngắn hoặc có từ mượn.

### 3.4. Transcript, timestamp và confidence

Transcript batch thường có hai lớp thông tin:

- `transcripts`: nội dung văn bản tổng hợp.
- `items`: từng từ hoặc dấu câu, kèm thời gian bắt đầu/kết thúc và confidence tùy kết quả.

Ứng dụng có thể dùng timestamp để đồng bộ phụ đề với video, tìm kiếm và nhảy tới đoạn audio tương ứng, tạo highlight theo từng từ, cắt đoạn audio để review và giữ liên kết giữa transcript với bản ghi gốc.

Confidence score là tín hiệu giúp ưu tiên kiểm tra, không phải chứng nhận câu nói đúng. Với tên riêng, số đơn hàng, mã sản phẩm hoặc từ chuyên ngành, cần đối chiếu nguồn dữ liệu nghiệp vụ.

### 3.5. Channel identification và speaker diarization

Hai tính năng này giải quyết hai vấn đề khác nhau:

- **Channel identification:** nhận diện người nói dựa trên channel audio riêng biệt. Ví dụ tổng đài stereo có channel của agent và customer. Khi bật `EnableChannelIdentification`, request phải khai báo `NumberOfChannels`.
- **Speaker diarization:** phân đoạn transcript theo người nói trong audio, ngay cả khi các speaker được trộn trong cùng channel. Kết quả có speaker label như `spk_0`, `spk_1`.

Channel identification hiện hỗ trợ audio tối đa hai channel; Transcribe không hỗ trợ media có hơn hai channel. Nếu thiết bị ghi âm đã tách mỗi người vào một channel riêng, channel identification thường cho cấu trúc rõ hơn. Nếu audio mono chứa nhiều người thay phiên nói, speaker diarization phù hợp hơn. Độ chính xác và khả năng sử dụng phụ thuộc ngôn ngữ, số người nói, thời gian chồng tiếng và chất lượng ghi âm.

### 3.6. Custom vocabulary và vocabulary filtering

**Custom vocabulary** giúp Transcribe nhận diện tốt hơn các thuật ngữ đặc thù:

- Tên sản phẩm, thương hiệu và tên riêng.
- Mã nội bộ, tên dự án và thuật ngữ kỹ thuật.
- Từ viết tắt hoặc cách đọc khác với từ điển phổ thông.

Từ vựng tùy chỉnh phải ở trạng thái `READY` trước khi dùng trong job. Ngôn ngữ của vocabulary phải khớp với language code của media. Nếu không khớp, Transcribe có thể bỏ qua vocabulary mà không trả lỗi.

**Vocabulary filtering** dùng danh sách từ để `MASK`, `REMOVE` hoặc `TAG` các từ cần xử lý theo policy. Đây là bộ lọc từ vựng, không phải bộ nhận diện PII toàn diện. Không dùng nó thay cho chính sách bảo vệ dữ liệu cá nhân.

### 3.7. Partial result và final result trong streaming

Streaming có thể trả về partial result trước khi câu nói hoàn tất. Các partial result có thể thay đổi khi dịch vụ nhận thêm audio.

- Chỉ lưu hoặc phát hành transcript khi result được đánh dấu final.
- Có thể bật partial-results stabilization để giảm thay đổi ở kết quả hiển thị, nhưng điều này có thể ảnh hưởng độ chính xác.
- Giữ `SessionId` và metadata session để đối chiếu log.
- Khi mất kết nối, cần xác định có tiếp tục session hay mở session mới; không nối hai luồng thành một transcript mà không giữ ranh giới.
- Nếu gửi partial text sang Translate, có thể dịch lặp nhiều lần và tạo bản dịch không ổn định. Hãy chờ câu/đoạn hoàn chỉnh trước khi xử lý tiếp.

### 3.8. PII và giới hạn redaction

Amazon Transcribe hỗ trợ nhận diện/redact PII cho một số ngôn ngữ nhất định. Tuy nhiên, trong bảng feature support hiện hành, `vi-VN` không có hỗ trợ redaction.

Vì vậy, với transcript tiếng Việt:

1. Giới hạn quyền truy cập audio và transcript thô.
2. Chỉ lưu những trường cần cho nghiệp vụ.
3. Tạo bước phát hiện và thay thế dữ liệu nhạy cảm riêng, phù hợp tiếng Việt và dữ liệu Việt Nam.
4. Có thể dùng quy tắc nghiệp vụ, kiểm tra định dạng và bước review của người có thẩm quyền.
5. Giữ bản gốc trong vùng lưu trữ được bảo vệ theo retention; chỉ cấp bản đã xử lý cho các hệ thống downstream.

Với ngôn ngữ được hỗ trợ, Transcribe có thể xuất transcript đã redacted và tùy cấu hình cả transcript chưa redacted. Hãy kiểm tra loại PII, ngôn ngữ và chế độ batch/streaming trước khi bật. Không giả định bật redaction sẽ che mọi thông tin nhận dạng.

## 4. Amazon Translate: dịch văn bản và tài liệu

Amazon Translate là dịch vụ machine translation. Dịch vụ nhận văn bản nguồn, mã ngôn ngữ nguồn/đích và trả văn bản đã dịch.

### 4.1. Real-time và asynchronous batch

| Tiêu chí | Real-time | Asynchronous batch |
|---|---|---|
| Request | Đồng bộ, nhận kết quả ngay | Bất đồng bộ, theo dõi job |
| Đầu vào | Đoạn text hoặc tài liệu được hỗ trợ | Tập tài liệu trong S3 |
| Đầu ra | Response hoặc tài liệu trả về | Tài liệu dịch trong S3 output prefix |
| Phù hợp | Chat, giao diện dịch, một đoạn transcript | Kho tài liệu, website, hàng nghìn file |
| Giới hạn | Text request tối đa 10.000 bytes | Hạn mức tài liệu, số file và tổng dung lượng lớn hơn |

Real-time translation phù hợp khi ứng dụng cần phản hồi nhanh cho một đoạn text. Batch translation phù hợp khi có tập tài liệu lớn và có thể xử lý nền.

Với real-time text translation, input tối đa 10.000 bytes UTF-8 theo quota mặc định hiện hành. Đừng coi 10.000 bytes là 10.000 ký tự: tiếng Việt có dấu dùng nhiều byte hơn ASCII. Hãy đo kích thước UTF-8 trước khi gọi API và chia văn bản theo ranh giới câu/đoạn khi cần.

### 4.2. Language code và automatic language detection

Ví dụ: tiếng Việt `vi`, tiếng Anh `en`, tiếng Nhật `ja` và tiếng Thái `th`.

Có thể đặt source language thành `auto` để dịch vụ tự nhận diện ngôn ngữ. Tự nhận diện có thể phát sinh chi phí riêng và không phải lúc nào cũng cần thiết. Nếu metadata nguồn đã biết ngôn ngữ, truyền language code cụ thể giúp kiểm soát quy trình tốt hơn.

Amazon Translate hỗ trợ nhiều language pair, nhưng một số tính năng chỉ áp dụng cho một tập con ngôn ngữ. Hãy xác nhận cặp nguồn/đích trước khi dùng tính năng tùy chỉnh.

### 4.3. Custom terminology

Custom terminology cho phép chỉ định cách dịch các thuật ngữ quan trọng:

| Source term | Target term | Lý do |
|---|---|---|
| My Business Shop | My Business Shop | Giữ nguyên tên thương hiệu |
| Redshift | Amazon Redshift | Bảo toàn tên sản phẩm |
| fulfillment center | trung tâm hoàn tất đơn hàng | Thống nhất thuật ngữ |
| order ID | mã đơn hàng | Dùng cách gọi nghiệp vụ nhất quán |

Custom terminology hữu ích cho tên thương hiệu/sản phẩm, thuật ngữ kỹ thuật, chức danh, cụm từ pháp lý, tài chính và chăm sóc khách hàng.

Terminology phải được import vào đúng Region, dùng đúng language pair và chỉ định trong request. Một request TranslateText hoặc batch translation job có thể tham chiếu tối đa một terminology resource theo quota hiện hành. Custom terminology là gợi ý theo ngữ cảnh, không bảo đảm target term luôn được sử dụng; hãy kiểm tra output với bộ câu kiểm thử nghiệp vụ.

### 4.4. Parallel data và Active Custom Translation

Parallel data là tập ví dụ gồm câu nguồn và bản dịch mong muốn. Amazon Translate dùng các ví dụ này để điều chỉnh phong cách, giọng điệu và cách chọn từ cho batch translation.

- Custom terminology kiểm soát cách dịch các thuật ngữ cụ thể.
- Parallel data hướng dẫn phong cách và cách diễn đạt trên nhiều câu/đoạn.

Parallel data phù hợp với văn bản có giọng thương hiệu, văn phong pháp lý hoặc thuật ngữ ngành. Tính năng Active Custom Translation dùng parallel data trong batch translation job; không nên mặc định có cùng khả năng cho mọi real-time request.

### 4.5. Các tùy chọn tùy chỉnh khác

Amazon Translate có một số tùy chọn:

- **Do-not-translate tags:** đánh dấu vùng HTML cần giữ nguyên.
- **Brevity:** rút gọn bản dịch cho real-time text translation; không hỗ trợ batch translation job.
- **Formality:** chọn văn phong trang trọng hoặc thân mật cho các ngôn ngữ được hỗ trợ.
- **Profanity masking:** che từ/cụm từ tục tĩu theo danh sách nhận diện của dịch vụ.
- **Parallel data:** điều chỉnh style, tone và word choice cho batch job.

Profanity masking hiện không hỗ trợ tiếng Việt. Ngoài ra, việc nhận diện profanity dựa trên từ/cụm từ, không hiểu hoàn toàn ngữ cảnh; có thể che nhầm từ vô hại trong một cụm từ. Nếu ứng dụng cần kiểm duyệt nội dung tiếng Việt, xây dựng policy riêng và đánh giá kết quả trước khi phát hành.

### 4.6. Batch translation và quota

Batch job đọc tài liệu từ S3, dịch theo một hoặc nhiều target language rồi ghi output vào S3. Quota mặc định hiện hành gồm:

- Tối đa 10 target languages trong một job.
- Tối đa 1.000.000 documents trong batch.
- Tổng kích thước batch tối đa 5 GB.
- Tối đa 10 batch jobs chạy đồng thời theo quota mặc định.
- Tối đa 1 MB phần văn bản có thể dịch trong một tài liệu và kích thước file tối đa 20 MB.

Đây là quota mặc định, có thể thay đổi hoặc được tăng qua Service Quotas/AWS Support. Kiểm tra quota của Region trước khi lên lịch batch lớn. Với workload lớn, dùng queue và concurrency control thay vì gửi tất cả request cùng lúc.

### 4.7. Dịch transcript mà vẫn giữ metadata

Khi dịch transcript có timestamp và speaker label, không nên gửi toàn bộ JSON vào Translate rồi ghi đè cấu trúc. Hãy tách phần văn bản cần dịch và giữ metadata bên ngoài.

~~~json
{
  "segmentId": "seg-00042",
  "speaker": "spk_1",
  "startMs": 12500,
  "endMs": 16800,
  "sourceLanguage": "vi",
  "sourceText": "Tôi sẽ gửi báo giá trong hôm nay.",
  "targetLanguage": "en",
  "translatedText": "I will send the quotation today."
}
~~~

Ứng dụng có thể dịch từng utterance hoặc đoạn đã hoàn chỉnh, rồi gắn kết quả vào `segmentId`. Bản dịch có thể thay đổi độ dài và trật tự từ; timestamp từ transcript nguồn không tự động trở thành timestamp chính xác của bản dịch.

## 5. Amazon Polly: text-to-speech

Amazon Polly chuyển text hoặc SSML thành audio tổng hợp. Ứng dụng có thể phát audio ngay sau khi nhận response hoặc lưu output để phân phối sau.

### 5.1. Chọn voice và engine

| Engine | Đặc điểm | Khi cân nhắc |
|---|---|---|
| Standard | Tổng hợp giọng nói tiêu chuẩn | Prompt ngắn, thông báo, workload nhạy chi phí |
| Neural | Giọng tự nhiên hơn cho nhiều ngôn ngữ/voice hỗ trợ | Nội dung người dùng nghe thường xuyên |
| Long-form | Tối ưu cho nội dung dài ở voice được hỗ trợ | Sách nói, bài học, narration dài |
| Generative | Giọng đọc tạo sinh, phù hợp trải nghiệm hội thoại ở voice hỗ trợ | Voice assistant, phản hồi hội thoại |

Không phải mọi voice hỗ trợ mọi engine. Cần kiểm tra ngôn ngữ, voice ID, engine, Region, SSML tag và quota. Dùng `DescribeVoices` để lấy voice catalog thay vì hardcode danh sách voice lâu dài.

### 5.2. Giới hạn tiếng Việt của Polly

Theo danh sách ngôn ngữ/voice hiện hành của Amazon Polly, Vietnamese không nằm trong các ngôn ngữ được hỗ trợ. Do đó:

- Polly không thể tổng hợp giọng đọc tiếng Việt trực tiếp.
- Nếu transcript tiếng Việt được dịch sang tiếng Anh, Polly có thể đọc bản dịch tiếng Anh bằng voice/engine tiếng Anh tương ứng.
- Nếu sản phẩm cần audio tiếng Việt, chọn một dịch vụ TTS khác có hỗ trợ tiếng Việt hoặc triển khai model TTS riêng trên hạ tầng phù hợp.
- Không dùng `LanguageCode=vi` hay tự đặt voice ID để vượt qua giới hạn ngôn ngữ.

Ví dụ: cuộc họp tiếng Việt được Transcribe thành `vi-VN`, Translate sang tiếng Anh bằng `vi` → `en`, sau đó Polly đọc bản tiếng Anh bằng voice `en-US`. Đây là luồng dịch và đọc lại bằng tiếng Anh, không phải Polly đọc tiếng Việt.

### 5.3. SynthesizeSpeech và asynchronous synthesis

**SynthesizeSpeech** phù hợp với đoạn văn bản ngắn, cần audio response ngay:

- Request tối đa 6.000 ký tự tổng cộng, trong đó tối đa 3.000 ký tự tính phí.
- Audio output của một request tối đa 10 phút; phần speech còn lại sẽ bị cắt. Dùng asynchronous synthesis hoặc streaming phù hợp cho nội dung dài.
- Hỗ trợ các engine tương ứng với voice được chọn.
- Có thể trả audio stream để client ghi ra file hoặc chuyển tiếp tới player.

**StartSpeechSynthesisTask** phù hợp với văn bản dài:

- Input tối đa 200.000 ký tự tổng cộng, trong đó tối đa 100.000 ký tự tính phí theo quota hiện hành.
- Task chạy bất đồng bộ.
- Audio hoặc speech marks được lưu trực tiếp vào S3.
- Có thể chỉ định SNS topic để nhận thông báo task hoàn tất.
- Theo dõi bằng `GetSpeechSynthesisTask` và `ListSpeechSynthesisTasks`.

Không chia văn bản dài tùy tiện theo số ký tự. Hãy cắt ở ranh giới câu/đoạn, giữ metadata thứ tự và ghép audio theo đúng thứ tự.

### 5.4. Bidirectional speech synthesis streaming

Polly có API `StartSpeechSynthesisStream` để gửi text từng phần và nhận audio từng phần qua HTTP/2:

- Chỉ dùng Generative engine.
- Phù hợp khi text được tạo dần, ví dụ voice assistant hoặc bản dịch real-time.
- Mỗi TextEvent tối đa 6.000 ký tự tổng cộng, trong đó tối đa 3.000 ký tự tính phí; không có giới hạn tổng ký tự cho toàn phiên stream.
- Không hỗ trợ speech marks.
- Cần SDK hỗ trợ bidirectional event stream; AWS CLI không hỗ trợ API này.

Chỉ chọn streaming khi ứng dụng thực sự có text đến theo từng đoạn và muốn phát audio trước khi toàn bộ nội dung hoàn tất.

### 5.5. SSML: kiểm soát cách đọc

Speech Synthesis Markup Language (SSML) cho phép điều khiển cách Polly phát âm:

- `break`: chèn khoảng nghỉ.
- `prosody`: điều chỉnh tốc độ, pitch và volume.
- `say-as`: hướng dẫn đọc số, ngày, ký hiệu hoặc định dạng đặc biệt.
- `phoneme`: hướng dẫn phát âm theo phonetic alphabet được hỗ trợ.
- `lang`: chỉ định ngôn ngữ cho một đoạn từ.
- `p`, `s`: tổ chức đoạn và câu.

~~~xml
<speak>
  <p>Hello and welcome.</p>
  <p>
    Your order number is
    <say-as interpret-as="characters">A B 1 2 3</say-as>.
  </p>
  <break time="500ms"/>
  <prosody rate="medium" volume="medium">
    Your package will arrive tomorrow.
  </prosody>
</speak>
~~~

Toàn bộ nội dung SSML phải nằm trong `<speak>`. Escape các ký tự dành riêng như `&`, `<` và `>` trong text. Danh sách tag hỗ trợ khác nhau giữa Standard, Neural, Long-form và Generative; kiểm tra compatibility trước khi triển khai.

### 5.6. Pronunciation lexicons và speech marks

Lexicon cho phép tùy chỉnh phát âm từ hoặc cụm từ, hữu ích với tên riêng, thương hiệu và thuật ngữ chuyên ngành. Lexicon được lưu theo Region, ngôn ngữ lexicon phải khớp ngôn ngữ voice và một request có thể áp dụng tối đa 5 lexicons theo quota hiện hành.

Speech marks là metadata mô tả vị trí từ, câu hoặc viseme trong audio. Có thể dùng để highlight từ đang được đọc, đồng bộ phụ đề, lip-sync nhân vật hoạt hình và đồng bộ timeline video. Speech marks được trả về trong request riêng, không phải cùng audio stream. Generative engine hiện không hỗ trợ speech marks; `StartSpeechSynthesisStream` cũng không hỗ trợ.

## 6. Tích hợp các dịch vụ trong kiến trúc AWS

### 6.1. Pipeline batch xử lý audio

~~~mermaid
flowchart TB
    U[Ứng dụng tải audio] --> S3[S3 raw audio]
    S3 --> EB[EventBridge]
    EB --> SF[Step Functions]
    SF --> T[Amazon Transcribe]
    T --> OUT[S3 transcript JSON]
    OUT --> N[Lambda normalize]
    N --> TR[Amazon Translate]
    TR --> TXT[S3 translated text]
    TXT --> P[Amazon Polly]
    P --> AUDIO[S3 synthesized audio]
    AUDIO --> CDN[CloudFront / API]
    N --> DB[DynamoDB metadata]
    TR --> DB
    P --> DB
~~~

Các thành phần:

- **Amazon S3:** lưu audio gốc, transcript, bản dịch và audio output theo prefix riêng.
- **Amazon EventBridge:** nhận sự kiện trạng thái job hoặc điều phối sự kiện.
- **AWS Step Functions:** điều phối các bước, retry, timeout, nhánh lỗi và trạng thái toàn pipeline.
- **AWS Lambda:** chuẩn hóa transcript, chia đoạn, kiểm tra metadata và gọi API phù hợp.
- **Amazon SQS:** đệm tác vụ, giới hạn tốc độ và tách producer/consumer.
- **Amazon SNS:** thông báo hoàn tất hoặc lỗi tới ứng dụng/người vận hành.
- **Amazon DynamoDB:** lưu job metadata, trạng thái, version và idempotency key.
- **Amazon CloudFront:** phân phối audio output theo policy truy cập.

Không nhất thiết phải dùng tất cả dịch vụ. Với ứng dụng nhỏ, Lambda + S3 + EventBridge có thể đủ. Với khối lượng lớn hoặc nhiều bước cần kiểm soát, Step Functions và SQS giúp quản lý retry/concurrency rõ hơn.

### 6.2. Sự kiện hoàn tất Transcribe

Amazon Transcribe có thể phát sự kiện trạng thái job qua EventBridge. Có thể tạo rule để gọi Lambda hoặc gửi message sang SQS khi job `COMPLETED` hoặc `FAILED`.

~~~json
{
  "source": ["aws.transcribe"],
  "detail-type": ["Transcribe Job State Change"],
  "detail": {
    "TranscriptionJobStatus": ["COMPLETED", "FAILED"]
  }
}
~~~

Khi nhận event, lấy `TranscriptionJobName` và trạng thái, kiểm tra event có thuộc job/version đang theo dõi không, xử lý output nếu `COMPLETED` hoặc lưu failure reason nếu `FAILED`. EventBridge phát sự kiện Transcribe theo cơ chế best-effort, vì vậy không dùng event làm nguồn trạng thái duy nhất: giữ job metadata và có bước reconciliation bằng `GetTranscriptionJob` khi event đến trễ hoặc không đến. Sự kiện có thể được gửi lại; không khởi chạy Translate/Polly lặp lại chỉ vì nhận cùng một event nhiều lần. S3 event notifications cũng có thể gửi trùng và không bảo đảm thứ tự; dùng `versionId`, object key và state store để deduplicate.

### 6.3. Idempotency và retry

Các API bất đồng bộ thường cần cơ chế điều phối riêng. Hãy lưu trạng thái theo `jobId`, `bucket`, `objectKey`, `versionId` hoặc `requestId`.

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> TRANSCRIBING
    TRANSCRIBING --> TRANSCRIBED
    TRANSCRIBING --> FAILED
    TRANSCRIBED --> TRANSLATING
    TRANSLATING --> TRANSLATED
    TRANSLATING --> FAILED
    TRANSLATED --> SYNTHESIZING
    SYNTHESIZING --> COMPLETED
    SYNTHESIZING --> FAILED
    FAILED --> RETRY_PENDING
    RETRY_PENDING --> TRANSCRIBING
    RETRY_PENDING --> TRANSLATING
    RETRY_PENDING --> SYNTHESIZING
    COMPLETED --> [*]
~~~

Quy tắc:

- Tạo job name duy nhất và lưu job name trước khi gọi dịch vụ.
- Không retry lỗi input không hợp lệ, language không hỗ trợ hoặc permission bị từ chối mà chưa sửa nguyên nhân.
- Dùng exponential backoff và jitter cho throttling/transient error.
- Đặt maximum attempts, timeout và DLQ.
- Lưu checkpoint sau từng bước để không phải transcribe lại nếu chỉ Polly thất bại.
- Gắn version cho transcript và translation; khi source thay đổi, đánh dấu output cũ là stale.

### 6.4. Real-time speech translation

~~~mermaid
sequenceDiagram
    participant C as Client
    participant T as Transcribe Streaming
    participant X as Translate
    participant P as Polly
    C->>T: Audio chunks
    T-->>C: Partial transcript
    T-->>X: Final utterance
    X-->>P: Translated text
    P-->>C: Audio response
~~~

Thiết kế cần lưu ý: chỉ chuyển utterance đã hoàn tất sang Translate; giữ speaker/channel metadata và thứ tự segment; dùng Translate real-time cho đoạn text nhỏ. Nếu text đến theo luồng, Polly `StartSpeechSynthesisStream` có thể nhận text incrementally nhưng chỉ hỗ trợ Generative engine và voice tương thích. Nếu voice đích không hỗ trợ Generative engine, dùng SynthesizeSpeech hoặc task bất đồng bộ với cách chunking phù hợp. Giới hạn queue và buffer để không tích lũy độ trễ vô hạn.

Nếu ngôn ngữ đích là tiếng Việt, Polly không có voice tương ứng trong danh sách hiện hành. Hãy chuyển sang TTS provider hỗ trợ tiếng Việt hoặc một model TTS được triển khai riêng.

### 6.5. Kết hợp các dịch vụ ngôn ngữ khác

Tùy đầu vào và mục tiêu sản phẩm, có thể bổ sung:

- **Amazon Textract:** trích xuất text, form và table từ ảnh/PDF trước khi dịch tài liệu. Giữ page number, bounding box và confidence để UI có thể đối chiếu bản dịch với tài liệu gốc.
- **Amazon Comprehend:** phân tích sentiment, entity, key phrase hoặc PII trên các ngôn ngữ/API được hỗ trợ. Ma trận ngôn ngữ khác nhau theo từng tính năng; không giả định PII detection của Comprehend hỗ trợ tiếng Việt chỉ vì Translate hỗ trợ `vi`.
- **Amazon Lex:** quản lý intent, slot và hội thoại cho chatbot/voice bot. Transcribe có thể cung cấp text đầu vào; Polly có thể đọc phản hồi khi ngôn ngữ đích có voice tương ứng.
- **Amazon Bedrock:** tóm tắt, phân loại hoặc tạo bản nháp từ transcript/bản dịch. Cần kiểm soát prompt injection trong transcript, quyền truy cập dữ liệu, grounding, Guardrails và human review cho nội dung có rủi ro.
- **Amazon Connect:** tích hợp luồng contact center, recording và các chức năng analytics/agent assistance. Tính năng của Connect có ma trận ngôn ngữ riêng; không suy ra Call Analytics của Transcribe hỗ trợ tiếng Việt.

Các dịch vụ bổ trợ có thể tạo thêm chi phí và bản sao dữ liệu. Chỉ chuyển trường dữ liệu cần thiết, giữ correlation ID giữa các bước và kiểm tra Region/feature support cho từng API.

## 7. Ví dụ tích hợp bằng AWS SDK for Java 2.x

### 7.1. Dependencies

Dùng AWS SDK for Java 2.x và quản lý phiên bản tập trung bằng AWS SDK BOM trong parent `pom.xml`. Thêm các module cần dùng:

~~~xml
<dependencies>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>transcribe</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>transcribestreaming</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>translate</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>polly</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>s3</artifactId>
    </dependency>
</dependencies>
~~~

Không đặt access key trực tiếp trong source code. Dùng default credential provider chain, IAM role của workload hoặc profile dành riêng cho môi trường phát triển.

### 7.2. Bắt đầu batch transcription cho audio tiếng Việt

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.transcribe.TranscribeClient;
import software.amazon.awssdk.services.transcribe.model.LanguageCode;
import software.amazon.awssdk.services.transcribe.model.Media;
import software.amazon.awssdk.services.transcribe.model.StartTranscriptionJobRequest;
import software.amazon.awssdk.services.transcribe.model.StartTranscriptionJobResponse;

public class StartVietnameseTranscription {
    public static void main(String[] args) {
        String jobName = "meeting-2026-11-20-001";

        try (TranscribeClient transcribe = TranscribeClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {

            StartTranscriptionJobRequest request =
                    StartTranscriptionJobRequest.builder()
                            .transcriptionJobName(jobName)
                            .languageCode(LanguageCode.VI_VN)
                            .media(Media.builder()
                                    .mediaFileUri(
                                        "s3://example-audio/raw/meeting.wav")
                                    .build())
                            .outputBucketName("example-transcripts")
                            .outputKey("transcripts/meeting-2026-11-20-001/")
                            .build();

            StartTranscriptionJobResponse response =
                    transcribe.startTranscriptionJob(request);

            System.out.println(
                    response.transcriptionJob().transcriptionJobStatus());
        }
    }
}
~~~

Đây là ví dụ khởi chạy job. Bucket audio phải tồn tại và quyền truy cập của Transcribe/caller phải phù hợp. Output bucket, KMS key và role phải được cấu hình theo security policy. Sau khi start, theo dõi trạng thái bằng `GetTranscriptionJob` hoặc EventBridge; không giả định transcript đã sẵn sàng ngay khi API trả response.

### 7.2.1. Cấu hình streaming transcription

Với Java SDK, dùng module `transcribestreaming`, `TranscribeStreamingAsyncClient` và `StartStreamTranscriptionRequest`. Phần publisher gửi audio chunk và response handler nhận transcript event cần được triển khai theo giao thức event stream của SDK:

~~~java
import java.util.concurrent.CompletableFuture;

import org.reactivestreams.Publisher;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.transcribestreaming.TranscribeStreamingAsyncClient;
import software.amazon.awssdk.services.transcribestreaming.model.AudioStream;
import software.amazon.awssdk.services.transcribestreaming.model.LanguageCode;
import software.amazon.awssdk.services.transcribestreaming.model.MediaEncoding;
import software.amazon.awssdk.services.transcribestreaming.model.PartialResultsStability;
import software.amazon.awssdk.services.transcribestreaming.model.StartStreamTranscriptionRequest;
import software.amazon.awssdk.services.transcribestreaming.model.StartStreamTranscriptionResponseHandler;

TranscribeStreamingAsyncClient client = TranscribeStreamingAsyncClient.builder()
        .region(Region.AP_SOUTHEAST_1)
        .build();

StartStreamTranscriptionRequest request =
        StartStreamTranscriptionRequest.builder()
                .languageCode(LanguageCode.VI_VN)
                .mediaEncoding(MediaEncoding.PCM)
                .mediaSampleRateHertz(16_000)
                .enablePartialResultsStabilization(true)
                .partialResultsStability(PartialResultsStability.MEDIUM)
                .build();

// audioPublisher phát PCM chunks; responseHandler xử lý TranscriptEvent.
CompletableFuture<Void> stream = client.startStreamTranscription(
        request, audioPublisher, responseHandler);
~~~

Đây là skeleton tích hợp; `audioPublisher` phải triển khai `Publisher<AudioStream>` và `responseHandler` phải là `StartStreamTranscriptionResponseHandler`. Cần đóng client/stream, xử lý backpressure, lỗi mạng, partial/final result và sample rate thực tế. Không bật partial stabilization nếu chưa đo trade-off giữa latency và độ chính xác.

### 7.3. Dịch văn bản tiếng Việt sang tiếng Anh

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.translate.TranslateClient;
import software.amazon.awssdk.services.translate.model.TranslateTextRequest;
import software.amazon.awssdk.services.translate.model.TranslateTextResponse;

public class TranslateVietnameseText {
    public static void main(String[] args) {
        String sourceText =
                "Tôi sẽ gửi báo giá và lịch giao hàng trong hôm nay.";

        try (TranslateClient translate = TranslateClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {

            TranslateTextRequest request =
                    TranslateTextRequest.builder()
                            .text(sourceText)
                            .sourceLanguageCode("vi")
                            .targetLanguageCode("en")
                            .build();

            TranslateTextResponse response =
                    translate.translateText(request);

            System.out.println(response.translatedText());
        }
    }
}
~~~

Ví dụ dùng real-time translation. Với transcript dài, hãy chia thành các segment có ngữ cảnh đủ lớn và giữ `segmentId` để nối bản dịch với timestamp/speaker. Nếu dùng terminology, thêm `TerminologyNames` theo API model và kiểm tra language pair.

### 7.4. Tổng hợp audio tiếng Anh bằng Polly

Vì Polly không hỗ trợ voice tiếng Việt hiện hành, ví dụ này đọc bản tiếng Anh đã được Translate tạo ra.

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.polly.PollyClient;
import software.amazon.awssdk.services.polly.model.Engine;
import software.amazon.awssdk.services.polly.model.OutputFormat;
import software.amazon.awssdk.services.polly.model.SynthesizeSpeechRequest;
import software.amazon.awssdk.services.polly.model.SynthesizeSpeechResponse;
import software.amazon.awssdk.services.polly.model.TextType;
import software.amazon.awssdk.services.polly.model.VoiceId;

public class SpeakTranslatedText {
    public static void main(String[] args) throws Exception {
        String translatedText =
                "I will send the quotation and delivery schedule today.";

        try (PollyClient polly = PollyClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {

            SynthesizeSpeechRequest request =
                    SynthesizeSpeechRequest.builder()
                            .engine(Engine.NEURAL)
                            .voiceId(VoiceId.JOANNA)
                            .outputFormat(OutputFormat.MP3)
                            .textType(TextType.TEXT)
                            .text(translatedText)
                            .build();

            try (ResponseInputStream<SynthesizeSpeechResponse> audio =
                         polly.synthesizeSpeech(request)) {
                Files.copy(
                        audio,
                        Path.of("translated-audio.mp3"),
                        StandardCopyOption.REPLACE_EXISTING);
            }
        }
    }
}
~~~

Voice ID và engine trong ví dụ phải được xác nhận bằng `DescribeVoices` tại Region đang dùng. `Joanna` là ví dụ cho tiếng Anh; không thay voice ID này bằng một chuỗi tự đặt để tạo giọng tiếng Việt.

### 7.5. AWS CLI: batch Transcribe, Translate và Polly

~~~bash
aws transcribe start-transcription-job \
  --region ap-southeast-1 \
  --transcription-job-name meeting-20261120-001 \
  --language-code vi-VN \
  --media MediaFileUri=s3://example-audio/raw/meeting.wav \
  --output-bucket-name example-transcripts \
  --output-key transcripts/meeting-20261120-001/
~~~

~~~bash
aws transcribe get-transcription-job \
  --region ap-southeast-1 \
  --transcription-job-name meeting-20261120-001
~~~

~~~bash
aws translate translate-text \
  --region ap-southeast-1 \
  --text "Tôi sẽ gửi báo giá trong hôm nay." \
  --source-language-code vi \
  --target-language-code en
~~~

~~~bash
aws polly synthesize-speech \
  --region ap-southeast-1 \
  --engine neural \
  --voice-id Joanna \
  --output-format mp3 \
  --text "I will send the quotation today." \
  translated-audio.mp3
~~~

Với tập tài liệu trong S3, có thể khởi chạy batch translation job:

~~~bash
aws translate start-text-translation-job \
  --region ap-southeast-1 \
  --input-data-config S3Uri=s3://example-translation/input/,ContentType=text/plain \
  --output-data-config S3Uri=s3://example-translation/output/ \
  --data-access-role-arn arn:aws:iam::123456789012:role/TranslateBatchRole \
  --source-language-code vi \
  --target-language-codes en ja
~~~

Role của batch job cần quyền đọc input prefix, ghi output prefix và quyền KMS phù hợp nếu S3 dùng SSE-KMS. Theo dõi job bằng `describe-text-translation-job`; xử lý trạng thái hoàn tất/lỗi qua orchestration.

Polly task bất đồng bộ cho narration dài:

~~~bash
aws polly start-speech-synthesis-task \
  --region ap-southeast-1 \
  --engine neural \
  --voice-id Joanna \
  --output-format mp3 \
  --output-s3-bucket-name example-audio-output \
  --output-s3-key-prefix narration/ \
  --text-type ssml \
  --text file://narration.ssml
~~~

Các lệnh là ví dụ. Thay bucket, key, Region và voice theo môi trường. Kiểm tra quyền S3, KMS, quota và engine compatibility trước khi chạy.

## 8. Bảo mật, quyền truy cập và quản lý dữ liệu

### 8.1. IAM least privilege

Tách quyền theo bước và theo workload:

| Thành phần | Quyền thường cần |
|---|---|
| API/backend khởi tạo Transcribe | `transcribe:StartTranscriptionJob`, `transcribe:GetTranscriptionJob` |
| Lambda xử lý kết quả | `s3:GetObject` trên transcript prefix, quyền ghi metadata cần thiết |
| Translate worker | `translate:TranslateText` hoặc quyền batch job tương ứng |
| Polly worker | `polly:SynthesizeSpeech` hoặc `polly:StartSpeechSynthesisTask` |
| Polly task output | Quyền ghi S3 và `sns:Publish` nếu dùng SNS notification |
| EventBridge | Quyền invoke target thông qua resource policy/role phù hợp |

Không cấp quyền `s3:*`, `transcribe:*`, `translate:*` hoặc `polly:*` trên toàn tài khoản chỉ để làm lab. Giới hạn theo action, resource, bucket/prefix và Region nếu service hỗ trợ.

### 8.2. Mã hóa và S3

Audio và transcript có thể chứa thông tin cá nhân hoặc dữ liệu nội bộ:

- Dùng HTTPS/TLS cho API.
- Bật S3 Block Public Access và bucket policy chặn truy cập công khai.
- Bật SSE-S3 hoặc SSE-KMS; dùng customer managed KMS key khi cần kiểm soát key policy/audit.
- Giới hạn quyền đọc raw audio và transcript chưa redacted.
- Dùng S3 versioning, lifecycle và retention theo policy.
- Không đưa transcript, email, số điện thoại hoặc token vào application log không cần thiết.
- Dùng signed URL có thời hạn nếu cần chia sẻ file với client.
- Đánh giá data residency, Region và yêu cầu compliance trước khi truyền audio ra ngoài hệ thống.

Transcribe hỗ trợ TLS cho dữ liệu truyền và có thể cấu hình KMS key cho output job. Nếu không chỉ định KMS key, output S3 có thể dùng SSE-S3 mặc định. Hãy kiểm tra encryption thực tế ở cả input bucket, output bucket và các bản sao downstream.

### 8.3. Data privacy của Amazon Translate

Tài liệu Translate hiện hành nêu rằng dữ liệu có thể được lưu để cải thiện chất lượng mô hình; có thể liên hệ AWS Support để yêu cầu xóa dữ liệu và yêu cầu dữ liệu tương lai của tài khoản không được lưu theo cơ chế được AWS hỗ trợ. Điều này có thể ảnh hưởng chất lượng mô hình được cải thiện từ dữ liệu.

Với dữ liệu nhạy cảm:

- Xác định data classification trước khi gọi Translate.
- Loại bỏ hoặc token hóa thông tin không cần thiết.
- Không gửi secret, password, access token hoặc dữ liệu thanh toán thô vào request.
- Kiểm tra chính sách dữ liệu của AWS và yêu cầu pháp lý của tổ chức.
- Dùng quy trình human review cho nội dung có hậu quả pháp lý/tài chính hoặc ảnh hưởng trực tiếp khách hàng.

### 8.4. Consent và retention audio

Nếu ghi âm cuộc gọi/cuộc họp, thông báo và lấy consent theo yêu cầu pháp lý/chính sách tổ chức; giới hạn mục đích và thời gian lưu; xác định ai có quyền nghe audio gốc; giữ audit trail cho việc tải xuống/xóa dữ liệu; có quy trình xóa audio và transcript đồng bộ khi hết retention hoặc có yêu cầu hợp lệ. Không mặc định transcript đã ẩn PII thì audio gốc không còn nhạy cảm.

## 9. Đảm bảo chất lượng đầu ra

### 9.1. Chất lượng transcription

Đo bằng các chỉ số:

- Word Error Rate (WER): tỷ lệ lỗi thay thế, chèn và xóa từ so với transcript chuẩn.
- Character Error Rate (CER): hữu ích với ngôn ngữ có biến thể dấu/ký tự.
- Language identification accuracy.
- Tỷ lệ segment có confidence thấp.
- Tỷ lệ tên riêng/mã sản phẩm được nhận dạng đúng.
- Độ trễ từ lúc audio kết thúc đến lúc transcript final sẵn sàng.

Với tiếng Việt, đánh giá cả dấu thanh, tên riêng, từ vay mượn, số điện thoại và mã đơn hàng. Transcript có confidence cao vẫn có thể sai một mã định danh quan trọng.

### 9.2. Chất lượng translation

Không chỉ kiểm tra câu có ngữ pháp đúng. Cần kiểm tra ý nghĩa, thuật ngữ sản phẩm, đại từ, vai trò người nói, sắc thái lịch sự, số, tiền tệ, ngày giờ, đơn vị, câu phủ định và ngoại lệ. Đoạn dịch phải giữ `segmentId` và speaker context.

Dùng custom terminology cho thuật ngữ cốt lõi, parallel data khi cần phong cách nhất quán và human review cho tài liệu có rủi ro cao.

### 9.3. Chất lượng TTS

Đánh giá pronunciation của tên riêng/từ viết tắt, intelligibility, naturalness, tốc độ, pitch, pause, volume, audio duration, sample rate, format, latency trước audio byte đầu tiên và khả năng đồng bộ speech marks với text.

Không dùng một voice/engine cho mọi ngữ cảnh. Voice đọc thông báo ngắn có thể khác voice phù hợp cho sách nói hoặc hội thoại.

## 10. Monitoring, reliability và chi phí

### 10.1. Chỉ số theo dõi

| Bước | Chỉ số | Mục tiêu |
|---|---|---|
| Upload | File count, size, invalid media | Phát hiện input lỗi |
| Transcribe | Job duration, failure rate, queue time, language | Đo khả năng nhận dạng |
| Translate | Request latency, throttling, batch completion, bytes/characters | Theo dõi throughput |
| Polly | Synthesis duration, task status, throttling, output size | Đo khả năng phát audio |
| Pipeline | End-to-end latency, retry count, DLQ depth | Đo độ tin cậy |
| Quality | WER/CER, translation review score, pronunciation score | Đảm bảo chất lượng |
| Cost | Cost/audio minute, cost/million chars, cost/output minute | Theo dõi unit economics |

Kết hợp CloudWatch metrics/logs, EventBridge events và metadata trong DynamoDB. Log nên có `jobId`, `segmentId`, service operation, duration và error code; không log toàn bộ transcript hoặc audio payload nếu không cần.

### 10.2. Chi phí

Ba dịch vụ tính phí theo đơn vị khác nhau:

| Dịch vụ | Đơn vị tính phí chính | Yếu tố làm tăng chi phí |
|---|---|---|
| Transcribe | Giây audio được xử lý | Tổng thời lượng, streaming/batch, feature add-on |
| Translate | Số ký tự được xử lý | Số ngôn ngữ đích, số lần retry, custom translation |
| Polly | Số ký tự được tổng hợp | Engine/voice, speech marks, số lần synthesis |

Cần cộng thêm S3 storage/request, data transfer, Lambda duration, Step Functions state transition, SQS/SNS, EventBridge, KMS request và chi phí lưu trữ/phân phối audio qua CDN.

Đo chi phí theo đơn vị nghiệp vụ như cost per audio minute, cost per translated million characters hoặc cost per generated audio minute. Không chỉ nhìn hóa đơn service mà bỏ qua phí orchestration và storage.

### 10.3. Giảm chi phí mà vẫn giữ chất lượng

- Dùng Transcribe batch cho file không cần kết quả real-time.
- Chỉ bật diarization, channel identification hoặc feature bổ sung khi có nhu cầu.
- Dùng Translate batch cho khối lượng tài liệu lớn.
- Lưu kết quả translation theo content hash để tránh dịch lại cùng nội dung.
- Cache Polly output theo text + voice + engine + SSML version.
- Dùng Polly asynchronous synthesis cho nội dung dài thay vì chia quá nhiều request nhỏ.
- Không gửi lại cùng segment khi nhận retry; dùng idempotency key.
- Đặt lifecycle cho raw audio, transcript và audio output theo retention.
- Theo dõi throttling và điều chỉnh concurrency thay vì tăng retry vô hạn.

## 11. Tình huống kiến trúc: tổng đài hỗ trợ khách hàng

Một doanh nghiệp có tổng đài tiếng Việt và nhóm hỗ trợ quốc tế cần lưu cuộc gọi, tạo transcript tiếng Việt, dịch transcript sang tiếng Anh, tạo bản đọc tiếng Anh cho nhân viên và tìm kiếm cuộc gọi theo mã đơn hàng/nội dung.

1. Hệ thống tổng đài lưu recording vào S3 raw audio.
2. EventBridge phát hiện object mới và khởi chạy Step Functions.
3. Transcribe batch dùng `vi-VN` để tạo transcript.
4. Lambda đọc transcript, giữ speaker/timestamp và chuẩn hóa segment.
5. Bước xử lý riêng kiểm tra PII tiếng Việt vì Transcribe redaction không hỗ trợ `vi-VN`.
6. Translate dùng `vi` → `en` và custom terminology cho tên sản phẩm.
7. Polly đọc bản dịch tiếng Anh bằng voice/engine được hỗ trợ.
8. S3 lưu transcript gốc, transcript đã xử lý, bản dịch và audio output theo prefix tách biệt.
9. DynamoDB lưu trạng thái, language, job ID, version và URI.
10. CloudFront hoặc API có xác thực cung cấp nội dung cho người dùng được phép.
11. CloudWatch theo dõi lỗi, latency, retry, quality sample và chi phí.

Nếu nhóm hỗ trợ yêu cầu nghe lại tiếng Việt, Polly không đáp ứng trực tiếp. Hãy tích hợp TTS provider khác có hỗ trợ tiếng Việt hoặc model TTS tự triển khai, đồng thời giữ cùng contract lưu output và metadata để không làm thay đổi toàn bộ pipeline.

## 12. Lab: xử lý một file audio tiếng Việt

Lab minh họa luồng batch, dịch sang tiếng Anh và tạo audio tiếng Anh. Dùng tài khoản sandbox, bucket riêng và audio không chứa thông tin nhạy cảm.

### Bước 1: chuẩn bị S3

Tạo các prefix `raw/`, `transcripts/`, `translations/` và `audio-en/`. Bật Block Public Access, encryption và policy chỉ cho role của lab truy cập.

### Bước 2: upload audio

~~~bash
aws s3 cp meeting.wav \
  s3://example-audio-lab/raw/meeting.wav
~~~

Đảm bảo file audio có chất lượng và định dạng được Transcribe hỗ trợ.

### Bước 3: tạo transcription job

~~~bash
aws transcribe start-transcription-job \
  --region ap-southeast-1 \
  --transcription-job-name lab-vietnamese-meeting \
  --language-code vi-VN \
  --media MediaFileUri=s3://example-audio-lab/raw/meeting.wav \
  --output-bucket-name example-audio-lab \
  --output-key transcripts/lab-vietnamese-meeting/
~~~

Kiểm tra trạng thái:

~~~bash
aws transcribe get-transcription-job \
  --region ap-southeast-1 \
  --transcription-job-name lab-vietnamese-meeting
~~~

Chờ trạng thái `COMPLETED`. Nếu `FAILED`, xem `FailureReason`, kiểm tra media URI, IAM, KMS và Region.

### Bước 4: đọc transcript

Lấy transcript URI từ `Transcript.TranscriptFileUri` trong job response. Tải file JSON về máy hoặc đọc từ S3 theo quyền được cấp.

~~~bash
aws s3 ls \
  s3://example-audio-lab/transcripts/lab-vietnamese-meeting/ \
  --recursive
~~~

Tìm phần `results.transcripts[0].transcript` để lấy văn bản tổng hợp. Nếu cần timestamp, speaker hoặc confidence, xử lý `results.items` và các metadata tương ứng.

### Bước 5: dịch sang tiếng Anh

~~~bash
aws translate translate-text \
  --region ap-southeast-1 \
  --text "Tôi sẽ gửi báo giá trong hôm nay." \
  --source-language-code vi \
  --target-language-code en
~~~

Với transcript dài, chia thành segment có ngữ cảnh, giữ thứ tự và ID. Nếu muốn batch, đưa tài liệu vào S3 và tạo `StartTextTranslationJob`.

### Bước 6: tạo audio tiếng Anh bằng Polly

~~~bash
aws polly synthesize-speech \
  --region ap-southeast-1 \
  --engine neural \
  --voice-id Joanna \
  --output-format mp3 \
  --text "I will send the quotation today." \
  translated-audio.mp3
~~~

~~~bash
aws s3 cp translated-audio.mp3 \
  s3://example-audio-lab/audio-en/translated-audio.mp3
~~~

### Bước 7: đánh giá

So sánh transcript với audio gốc; kiểm tra tên riêng và số liệu; so sánh bản dịch với ý nghĩa nguồn; nghe audio tiếng Anh và kiểm tra phát âm; ghi lại latency, lỗi, thời lượng audio và số ký tự đã xử lý.

Lab không tạo audio tiếng Việt bằng Polly vì ngôn ngữ này chưa có trong danh sách voice được hỗ trợ.

## 13. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Transcribe AccessDenied | Role, S3 bucket policy hoặc KMS | Kiểm tra input/output bucket, role và key policy |
| Transcribe BadRequestException | Language code, media encoding, sample rate hoặc cấu hình channel không hợp lệ | Kiểm tra request và audio metadata |
| Transcribe nhận sai từ chuyên ngành | Audio kém, vocabulary chưa phù hợp, language mismatch | Làm sạch audio, kiểm tra vocabulary state/language |
| Transcript không có speaker label | Chưa bật diarization hoặc language/feature không hỗ trợ | Kiểm tra feature matrix và request |
| Transcript tiếng Việt vẫn chứa PII | `vi-VN` không hỗ trợ Transcribe redaction | Thêm bước xử lý PII riêng và review |
| Streaming partial thay đổi | Partial result chưa final | Chỉ commit result final |
| Translate UnsupportedLanguagePairException | Cặp ngôn ngữ hoặc feature không được hỗ trợ | Kiểm tra supported language pair |
| Translate throttling | Gửi request quá nhanh hoặc vượt quota | Giảm concurrency, backoff, request quota increase |
| Translate request quá lớn | Vượt 10.000 bytes real-time hoặc quota document | Chia theo câu/đoạn và đo UTF-8 bytes |
| Bản dịch sai thuật ngữ | Thiếu terminology hoặc context | Bổ sung terminology/parallel data và human review |
| Polly báo voice/engine không hợp lệ | Voice không hỗ trợ engine hoặc Region | Dùng DescribeVoices và kiểm tra compatibility |
| Polly không đọc được tiếng Việt | Vietnamese không nằm trong voice catalog | Dùng TTS khác hoặc dịch sang ngôn ngữ Polly hỗ trợ |
| Polly output bị cắt | Vượt giới hạn sync hoặc thời lượng audio | Dùng StartSpeechSynthesisTask hoặc streaming API phù hợp |
| Polly pronunciation sai | Text/SSML/lexicon chưa phù hợp | Kiểm tra SSML support và pronunciation lexicon |
| Job chạy lặp | Event duplicate hoặc retry không idempotent | Dùng job ID, object version và state store |
| Pipeline bị backlog | Downstream chậm hơn upstream | Dùng SQS, giới hạn concurrency và theo dõi queue age |

## 14. Những sai lầm thường gặp

**Giả định một ngôn ngữ có ở cả ba dịch vụ.** Mỗi service có catalog và feature matrix riêng. Kiểm tra language support trước khi thiết kế.

**Dùng Transcribe redaction cho transcript tiếng Việt.** `vi-VN` hiện không hỗ trợ redaction. Cần bước bảo vệ PII riêng.

**Bật profanity masking cho Translate tiếng Việt.** Feature này không hỗ trợ `vi`. Dùng lớp moderation khác phù hợp với yêu cầu.

**Cho rằng Polly đọc được tiếng Việt.** Polly không có Vietnamese voice trong catalog hiện hành. Dùng TTS khác hoặc chuyển ngôn ngữ đích sang voice được hỗ trợ.

**Dịch từng partial result.** Partial text có thể thay đổi, dẫn đến bản dịch trùng và sai. Chỉ gửi final utterance hoặc segment đã hoàn chỉnh.

**Dịch JSON transcript nguyên khối.** Có thể làm hỏng timestamp, speaker ID và cấu trúc. Chỉ dịch trường văn bản, giữ metadata riêng.

**Coi confidence score là bằng chứng chắc chắn.** Dùng confidence để ưu tiên review, không thay cho kiểm tra nghiệp vụ.

**Dùng Polly SynthesizeSpeech cho sách nói dài.** Dùng asynchronous synthesis hoặc streaming API phù hợp.

**Retry mọi lỗi vô hạn.** Lỗi permission, language và input không hợp lệ cần sửa nguyên nhân; retry vô hạn chỉ tăng chi phí.

**Không lưu version của nội dung.** Khi audio/transcript thay đổi, translation và audio cũ có thể không còn tương ứng. Lưu content hash/version và trạng thái stale.

## 15. Câu hỏi tự kiểm tra

1. Amazon Transcribe, Translate và Polly giải quyết ba bài toán nào?
2. Khi nào dùng batch transcription và khi nào dùng streaming?
3. `vi-VN` và `vi` được dùng trong dịch vụ nào?
4. Vì sao phải kiểm tra feature matrix theo từng ngôn ngữ?
5. Channel identification khác speaker diarization như thế nào?
6. Custom vocabulary và vocabulary filtering có mục đích gì?
7. Partial result trong streaming có thể thay đổi ra sao?
8. Vì sao không nên dịch partial transcript?
9. Transcribe có tự động redaction PII cho tiếng Việt không?
10. Amazon Translate real-time khác batch translation như thế nào?
11. Custom terminology khác parallel data ra sao?
12. Brevity của Translate dùng được cho batch translation không?
13. Profanity masking của Translate có hỗ trợ tiếng Việt không?
14. Vì sao 10.000 bytes không đồng nghĩa 10.000 ký tự tiếng Việt?
15. Polly Standard, Neural, Long-form và Generative khác nhau thế nào?
16. `SynthesizeSpeech` khác `StartSpeechSynthesisTask` như thế nào?
17. Khi nào dùng `StartSpeechSynthesisStream`?
18. SSML giúp kiểm soát speech output ra sao?
19. Speech marks có thể dùng cho trải nghiệm UI nào?
20. Vì sao Polly không thể tạo giọng đọc tiếng Việt trong catalog hiện hành?
21. EventBridge giúp điều phối job Transcribe như thế nào?
22. Vì sao S3 event và job event cần idempotency?
23. IAM role và KMS key tham gia bảo vệ pipeline ở đâu?
24. WER/CER dùng để đánh giá chất lượng transcription như thế nào?
25. Cần đo những đơn vị nào để tính chi phí end-to-end?

## 16. Checklist production

- [ ] Đã xác nhận language code và feature support cho từng dịch vụ.
- [ ] Đã chọn batch hoặc streaming theo latency target.
- [ ] Audio encoding/sample rate khớp dữ liệu thực tế.
- [ ] Có quy trình xử lý partial/final result.
- [ ] Có kiểm tra speaker/channel và vocabulary khi cần.
- [ ] Đã xác nhận PII redaction hỗ trợ đúng ngôn ngữ; tiếng Việt có bước thay thế riêng.
- [ ] Translate có custom terminology và review cho thuật ngữ quan trọng.
- [ ] Đã xác nhận quota real-time/batch và giới hạn UTF-8 bytes.
- [ ] Polly voice, engine, Region và SSML tags đã được kiểm thử.
- [ ] Không giả định Polly hỗ trợ tiếng Việt.
- [ ] Job state, retry, timeout và DLQ được cấu hình.
- [ ] EventBridge/S3 event có idempotency key và deduplication.
- [ ] Audio/transcript/translation/output có version và retention.
- [ ] IAM least privilege, S3 Block Public Access và KMS encryption được cấu hình.
- [ ] Log không chứa audio payload hoặc transcript nhạy cảm không cần thiết.
- [ ] Có consent, retention và quy trình xóa dữ liệu.
- [ ] Có dashboard latency, error, queue depth, throttling và cost.
- [ ] Có đánh giá WER/CER, translation review và TTS pronunciation.
- [ ] Có human review cho nội dung rủi ro cao.
- [ ] Đã chạy restore/replay test và xác minh output không bị nhân bản.

## Kết luận

Amazon Transcribe, Amazon Translate và Amazon Polly tạo thành bộ công cụ xử lý ngôn ngữ hữu ích khi mỗi bước được chọn đúng theo loại dữ liệu, latency, ngôn ngữ và tính năng hỗ trợ. Transcribe chuyển audio thành transcript, Translate chuyển văn bản giữa các ngôn ngữ, Polly tạo audio từ văn bản/SSML.

Với tiếng Việt, Transcribe hỗ trợ batch và streaming, Translate hỗ trợ dịch văn bản, nhưng Transcribe chưa hỗ trợ PII redaction cho `vi-VN`, Translate chưa hỗ trợ profanity masking cho `vi`, và Polly chưa có voice tiếng Việt trong catalog hiện hành. Những giới hạn này phải được phản ánh ngay trong kiến trúc. Kết hợp S3, EventBridge, Step Functions, Lambda, SQS, SNS và DynamoDB giúp pipeline có thể mở rộng, phục hồi và quan sát tốt hơn. Bảo mật dữ liệu, chất lượng ngôn ngữ, idempotency và chi phí cần được thiết kế cùng lúc với chức năng.

## Tài liệu AWS tham khảo

- [Amazon Transcribe Developer Guide](https://docs.aws.amazon.com/transcribe/latest/dg/what-is.html)
- [Supported languages and language-specific features — Transcribe](https://docs.aws.amazon.com/transcribe/latest/dg/supported-languages.html)
- [Amazon Transcribe feature matrix](https://docs.aws.amazon.com/transcribe/latest/dg/feature-matrix.html)
- [Batch transcription jobs](https://docs.aws.amazon.com/transcribe/latest/dg/how-input.html)
- [Transcribing streaming audio](https://docs.aws.amazon.com/transcribe/latest/dg/streaming.html)
- [StartStreamTranscription API](https://docs.aws.amazon.com/transcribe/latest/APIReference/API_streaming_StartStreamTranscription.html)
- [Channel identification](https://docs.aws.amazon.com/transcribe/latest/dg/channel-id.html)
- [Speaker diarization](https://docs.aws.amazon.com/transcribe/latest/dg/diarization.html)
- [Using a custom vocabulary](https://docs.aws.amazon.com/transcribe/latest/dg/custom-vocabulary-using.html)
- [Redacting or identifying PII](https://docs.aws.amazon.com/transcribe/latest/dg/pii-redaction.html)
- [Data encryption — Transcribe](https://docs.aws.amazon.com/transcribe/latest/dg/data-encryption.html)
- [Using EventBridge with Transcribe](https://docs.aws.amazon.com/transcribe/latest/dg/monitoring-events.html)
- [Streaming Transcribe examples using SDK for Java 2.x](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_transcribe-streaming_code_examples.html)
- [Amazon Transcribe pricing](https://aws.amazon.com/transcribe/pricing/)
- [Amazon Translate Developer Guide](https://docs.aws.amazon.com/translate/latest/dg/what-is.html)
- [Supported languages and language codes — Translate](https://docs.aws.amazon.com/translate/latest/dg/what-is-languages.html)
- [Translation processing modes](https://docs.aws.amazon.com/translate/latest/dg/processing.html)
- [Customizing translations](https://docs.aws.amazon.com/translate/latest/dg/customizing-translations.html)
- [Masking profanity in Amazon Translate](https://docs.aws.amazon.com/translate/latest/dg/customizing-translations-profanity.html)
- [Custom terminology](https://docs.aws.amazon.com/translate/latest/dg/how-custom-terminology.html)
- [Parallel data and Active Custom Translation](https://docs.aws.amazon.com/translate/latest/dg/customizing-translations-parallel-data.html)
- [Running a batch translation job](https://docs.aws.amazon.com/translate/latest/dg/async-start.html)
- [Guidelines and quotas — Translate](https://docs.aws.amazon.com/translate/latest/dg/what-is-limits.html)
- [Amazon Translate pricing](https://aws.amazon.com/translate/pricing/)
- [Amazon Polly Developer Guide](https://docs.aws.amazon.com/polly/latest/dg/what-is.html)
- [Languages in Amazon Polly](https://docs.aws.amazon.com/polly/latest/dg/supported-languages.html)
- [Available voices](https://docs.aws.amazon.com/polly/latest/dg/available-voices.html)
- [Generative voices](https://docs.aws.amazon.com/polly/latest/dg/generative-voices.html)
- [Long-form voices](https://docs.aws.amazon.com/polly/latest/dg/long-form-voices.html)
- [Generating speech with SSML](https://docs.aws.amazon.com/polly/latest/dg/ssml.html)
- [Supported SSML tags](https://docs.aws.amazon.com/polly/latest/dg/supportedtags.html)
- [Speech marks](https://docs.aws.amazon.com/polly/latest/dg/speechmarks.html)
- [Long audio files and asynchronous synthesis](https://docs.aws.amazon.com/polly/latest/dg/asynchronous.html)
- [SynthesizeSpeech and StartSpeechSynthesisStream comparison](https://docs.aws.amazon.com/polly/latest/dg/bidirectional-streaming-choosing.html)
- [Polly quotas](https://docs.aws.amazon.com/polly/latest/dg/limits.html)
- [Amazon Polly pricing](https://aws.amazon.com/polly/pricing/)
- [AWS SDK for Java 2.x — Transcribe examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_transcribe_code_examples.html)
- [AWS SDK for Java 2.x — Translate examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_translate_code_examples.html)
- [AWS SDK for Java 2.x — Polly examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_polly_code_examples.html)
- [AWS Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html)
- [Amazon EventBridge](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-what-is.html)
- [Amazon S3 Event Notifications](https://docs.aws.amazon.com/AmazonS3/latest/userguide/EventNotifications.html)
- [Amazon Textract Developer Guide](https://docs.aws.amazon.com/textract/latest/dg/what-is.html)
- [Amazon Comprehend Developer Guide](https://docs.aws.amazon.com/comprehend/latest/dg/what-is.html)
- [Amazon Lex V2 Developer Guide](https://docs.aws.amazon.com/lexv2/latest/dg/what-is.html)
- [Amazon Bedrock User Guide](https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html)
- [Amazon Connect Administrator Guide](https://docs.aws.amazon.com/connect/latest/adminguide/what-is-amazon-connect.html)
- [AWS Pricing Calculator](https://calculator.aws/)

