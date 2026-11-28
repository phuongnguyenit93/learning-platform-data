# Chất lượng khi vận hành: Ngăn phản hồi chưa xác minh tự động trở thành đáp án chuẩn

## 1. Vì sao phản hồi người dùng không tự động là sự thật?

Ứng dụng AI thường nhận được nhiều loại phản hồi: thumbs up/down, đánh giá sao, lời phàn nàn, câu trả lời người dùng đề xuất, nội dung họ sửa lại, thao tác hoàn tất hoặc hủy bỏ, và kết quả nghiệp vụ sau khi assistant gọi tool. Những tín hiệu này hữu ích để phát hiện vấn đề, nhưng không phải tất cả đều chứng minh câu trả lời đúng hay sai.

Ví dụ:

- Người dùng bấm thumbs up vì câu trả lời ngắn và dễ đọc, dù một con số trong đó sai.
- Người dùng bấm thumbs down vì không thích chính sách được trích dẫn, dù câu trả lời phản ánh đúng chính sách hiện hành.
- Người dùng sửa câu trả lời theo một cách diễn đạt họ thích, nhưng bản sửa lại bỏ mất điều kiện quan trọng.
- Một tài khoản gửi hàng trăm phản hồi cùng hướng để thao túng dữ liệu đánh giá.
- Một LLM judge chấm PASS, rồi kết quả PASS đó được đưa vào dataset làm nhãn chuẩn cho lần hiệu chuẩn judge tiếp theo. Hệ thống đang tự xác nhận chính mình.
- Một tài liệu RAG chứa chỉ dẫn hoặc thông tin sai được đưa vào pipeline rồi trở thành “đáp án đúng” chỉ vì model đã sử dụng nó.

Nếu các tín hiệu này được tự động chuyển thành golden labels, dataset sẽ dần chứa preference, lỗi, nội dung cũ hoặc dữ liệu bị thao túng. Prompt/model mới sau đó có thể được tối ưu theo nhãn sai và làm lỗi lan rộng qua nhiều phiên bản.

**Nguyên tắc cốt lõi:** feedback là một quan sát cần được kiểm tra; golden label là một kết luận có evidence, phạm vi, provenance, người chịu trách nhiệm và phiên bản rõ ràng.

Bài học thuộc chương **Chất lượng khi vận hành** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool calling; đồng thời theo dõi metrics, traces, chi phí và độ trễ để phát hiện suy giảm qua các phiên bản prompt, model và pipeline.

Sau bài học, bạn có thể:

- Phân biệt user feedback, behavioral signals, evaluator verdict, verified labels và golden answers.
- Xác định phản hồi nào chỉ thể hiện preference, phản hồi nào là một factual claim cần xác minh.
- Thiết kế pipeline quarantine–triage–verify–adjudicate–promote.
- Gắn nhãn với source of truth, evidence snapshot, thời điểm hiệu lực và provenance.
- Ngăn self-training loop, brigading, duplicate feedback và data poisoning.
- Dùng Spring AI Evaluator như một tín hiệu tự động có version, không coi nó là ground truth.
- Xây dựng approval gate và audit trail trước khi đưa case vào golden dataset.
- Tách dataset development, calibration, validation và held-out test để tránh leakage.
- Theo dõi chất lượng feedback pipeline và thu hồi các nhãn bị phát hiện sai.

## 2. Phân biệt các loại tín hiệu

Một hệ thống đánh giá nên lưu nguồn tín hiệu riêng biệt. Không gộp tất cả thành một field isCorrect.

| Tín hiệu | Ví dụ | Điều có thể suy ra | Điều chưa thể kết luận |
| --- | --- | --- | --- |
| Explicit rating | Thumbs up/down, 1–5 sao | Mức hài lòng được người dùng tự báo | Tính đúng đắn của từng claim |
| Free-text feedback | “Câu trả lời thiếu bước xác nhận” | Một vấn đề hoặc kỳ vọng cần điều tra | Nội dung phàn nàn chắc chắn đúng |
| User correction | “Mã đơn đúng là X” | Một factual claim mới cần kiểm tra | Người gửi có quyền hoặc dữ liệu chính xác |
| Behavioral signal | Copy, retry, abandon, click | Hành vi trong UI | Nguyên nhân hoặc mức độ hài lòng |
| Business outcome | Tool xác nhận giao dịch hoàn tất | Kết quả trong hệ thống nghiệp vụ tại một thời điểm | Toàn bộ câu trả lời có đúng và đầy đủ |
| LLM evaluator | Relevance PASS, fact-check FAIL | Nhận định tự động theo model/rubric cụ thể | Nhãn chuẩn độc lập |
| Human annotation | Reviewer chấm theo rubric | Phán đoán có quy trình của người đánh giá | Sự thật nếu thiếu chuyên môn hoặc evidence |
| Adjudicated label | Kết luận sau phân xử | Nhãn đã qua quy trình xác minh đã định | Chân lý vĩnh viễn ngoài phạm vi và thời điểm |

### 2.1. Feedback preference khác feedback correctness

Một rating thấp có thể phản ánh:

- Câu trả lời khó đọc.
- Thời gian phản hồi lâu.
- Người dùng không đồng ý với kết quả.
- Assistant không hiểu ý định.
- Kết quả đúng nhưng không đáp ứng kỳ vọng.
- Một lỗi factual hoặc một hành động tool sai.

Vì vậy, rating nên được lưu như **USER_SATISFACTION_SIGNAL**. Nếu người dùng gửi correction cụ thể, lưu riêng thành **USER_ASSERTED_CORRECTION** để kiểm tra. Không tự chuyển rating hoặc correction thành GOLD_PASS/GOLD_FAIL.

### 2.2. Behavioral signal không có ý nghĩa duy nhất

Người dùng copy câu trả lời có thể vì câu trả lời hữu ích, hoặc vì muốn chuyển cho người khác kiểm tra. Người dùng retry có thể vì câu trả lời sai, hoặc chỉ muốn hỏi theo cách khác. Người dùng rời trang có thể đã hoàn thành nhiệm vụ hoặc bị mất kết nối.

Behavioral signals có thể giúp chọn case để review, nhưng không tự xác định nhãn correctness.

### 2.3. Business outcome cần đúng scope

Nếu order service xác nhận đơn hàng đã giao, đó là evidence mạnh cho claim “đơn hàng đã giao” tại thời điểm đọc. Nó không chứng minh các phần khác của câu trả lời như chính sách hoàn tiền hoặc thời hạn bảo hành.

Luôn nối business outcome với record version, tenant, authorization scope và event time. Một status hiện tại không thể thay thế status lịch sử khi đánh giá câu trả lời đã được tạo trước đó.

## 3. Golden answer, golden label và reference answer

Ba khái niệm thường bị dùng lẫn nhau:

- **Golden label:** nhãn đã được xác minh cho một dimension, ví dụ relevance = PASS hoặc claim X = UNSUPPORTED.
- **Reference answer:** một câu trả lời mẫu có thể dùng để so sánh hoặc làm ví dụ.
- **Golden answer:** cách gọi thông dụng cho câu trả lời tham chiếu đã được chấp nhận theo rubric và phạm vi cụ thể.

Với câu hỏi ngôn ngữ tự nhiên, có thể có nhiều câu trả lời đều đúng. Một reference answer không nhất thiết là câu duy nhất được phép. Golden dataset thường nên ưu tiên labels, rubric, evidence và các acceptance criteria; chỉ lưu exact expected answer khi bài toán thực sự có đáp án duy nhất, ví dụ một phép tính hoặc một field lấy từ source of truth.

Một nhãn chuẩn phải trả lời được:

1. Đang đánh giá dimension nào?
2. Input và response snapshot nào?
3. Evidence/source nào hỗ trợ kết luận?
4. Evidence có hiệu lực ở thời điểm nào?
5. Rubric/policy version nào được áp dụng?
6. Ai hoặc quy trình nào xác minh?
7. Nhãn được phê duyệt vào lúc nào?
8. Dataset version nào chứa nhãn này?

Không dùng một nhãn correct=true chung cho relevance, factuality, completeness, safety và task success.

## 4. Vòng đời của feedback trước khi được promote

Feedback cần qua các trạng thái rõ ràng. Trạng thái “đã nhận” không đồng nghĩa “đã xác minh”.

~~~mermaid
flowchart TD
    RAW["Feedback received"] --> Q["QUARANTINED"]
    Q --> N["Normalize, redact, deduplicate"]
    N --> T["TRIAGED"]
    T -->|Preference only| P["Store as preference signal"]
    T -->|Factual claim / defect| V["Verify against trusted evidence"]
    V -->|Insufficient| I["NEEDS_EVIDENCE"]
    V -->|Contradicted / invalid| R["REJECTED"]
    V -->|Supported| H["Human review / adjudication"]
    H -->|Unresolved| U["UNRESOLVED"]
    H -->|Accepted| C["GOLD_CANDIDATE"]
    C --> A["Independent approval gate"]
    A --> G["GOLDEN DATASET VERSION"]
    G --> M["Monitor, audit and revoke if needed"]
~~~

Một state machine gợi ý:

| Trạng thái | Ý nghĩa | Có được dùng làm gold label? |
| --- | --- | --- |
| RECEIVED | Đã nhận event | Không |
| QUARANTINED | Đang chờ kiểm tra nguồn, quyền và nội dung | Không |
| NORMALIZED | Đã chuẩn hóa schema, redaction và dedup | Không |
| TRIAGED | Đã phân loại loại feedback và mức rủi ro | Không |
| NEEDS_EVIDENCE | Thiếu source hoặc snapshot để xác minh | Không |
| VERIFIED | Claim được đối chiếu với evidence phù hợp | Chưa tự động |
| ADJUDICATED | Bất đồng đã được phân xử theo protocol | Có thể trở thành candidate |
| GOLD_CANDIDATE | Đủ điều kiện chờ phê duyệt dataset | Chưa |
| GOLDEN | Đã được promote vào dataset version bất biến | Có |
| REJECTED | Claim sai, không hợp lệ hoặc không đủ điều kiện | Không |
| UNRESOLVED | Không thể kết luận trong phạm vi hiện tại | Không |
| REVOKED | Nhãn từng được dùng nhưng sau đó bị thu hồi | Không dùng trong benchmark hiện hành |

VERIFIED chỉ mô tả kết quả kiểm tra evidence cho claim cụ thể. Dataset promotion còn cần rubric, scope, quyền sử dụng, provenance và approval. Tách hai khái niệm giúp tránh biến một kiểm tra kỹ thuật thành quyết định quản trị dataset.

## 5. Phân loại độ tin cậy của nguồn

Không có một thứ hạng nguồn đúng cho mọi domain. Một nguồn có thẩm quyền trong nghiệp vụ này có thể không có thẩm quyền trong nghiệp vụ khác.

| Nguồn | Ví dụ | Cách dùng |
| --- | --- | --- |
| System of record | Order DB, payment ledger, inventory service | Xác minh trạng thái nghiệp vụ theo record/time/version |
| Approved policy source | Policy repository có owner và effective date | Xác minh quy định và điều kiện áp dụng |
| Signed/verified source document | Tài liệu được owner phê duyệt, có version | Kiểm tra claim gắn với source snapshot |
| Domain expert review | Reviewer có chuyên môn và quyền phù hợp | Đánh giá nuance hoặc trường hợp không có máy kiểm tra |
| Independent human annotation | Reviewer độc lập theo rubric | Tạo label sau khi evidence đã được cung cấp |
| User correction | Người dùng đề xuất thông tin khác | Tạo claim cần xác minh, không tự động xác nhận |
| LLM judge | FactCheckingEvaluator hoặc custom judge | Tín hiệu hỗ trợ triage và phát hiện bất đồng |
| Behavioral feedback | Rating, retry, copy, abandonment | Phân tích trải nghiệm và chọn mẫu review |
| Model-generated answer | Câu trả lời từ chính model đang được đánh giá | Không dùng làm nguồn độc lập để tự xác nhận |

### 5.1. Xác minh source of truth theo domain

Ví dụ:

- Trạng thái thanh toán: payment ledger hoặc payment provider record có transaction reference.
- Trạng thái giao hàng: logistics event stream hoặc order system.
- Chính sách hiện hành: policy version có ngày hiệu lực và owner.
- Câu hỏi kiến thức tổng quát: nguồn tham khảo được domain owner chấp nhận và có timestamp.
- Chất lượng diễn đạt: rubric và reviewer được calibration, không có một database nào tự quyết định.

Không dùng một tài liệu bất kỳ trong vector store làm nguồn chuẩn chỉ vì retriever trả về nó. Cần xác minh source owner, version, trust boundary và thời gian hiệu lực.

### 5.2. Temporal validity

Một claim có thể đúng hôm qua nhưng sai hôm nay. Lưu riêng:

- observedAt: lúc hệ thống ghi nhận evidence.
- validFrom / validTo: khoảng thời gian evidence có hiệu lực nếu domain hỗ trợ.
- interactionOccurredAt: lúc response được tạo.
- verifiedAt: lúc reviewer hoặc process xác minh.
- sourceVersion: version của record/document/policy.

Khi chấm câu trả lời cũ, dùng evidence có hiệu lực tại thời điểm câu trả lời được tạo. Không truy vấn trạng thái hiện tại rồi kết luận ngược về quá khứ.

## 6. Provenance: mỗi nhãn phải truy về được nguồn

Provenance mô tả dữ liệu đến từ đâu, được biến đổi thế nào và ai đã đưa ra quyết định. Với golden dataset, provenance quan trọng không kém label value.

Một label record nên giữ:

- Feedback/event ID và interaction/assistant-turn reference.
- Feedback type và channel.
- Source principal reference đã pseudonymize.
- Tenant scope và authorization decision reference.
- Input/response/evidence snapshot references.
- Source system, source record ID và source version.
- Content hash hoặc immutable object version.
- Acquisition time, event time và valid time.
- Redaction/normalization pipeline version.
- Deduplication key và linked duplicate IDs.
- Rubric version và evaluator version.
- Reviewer/adjudicator reference và role.
- Decision reason code, approval timestamp.
- Dataset version, split và usage history.

Không cần copy raw content vào mọi record. Dùng immutable evidence references tới kho được bảo vệ, có access control và retention.

### 6.1. Evidence phải gắn với claim

Một document dài có thể chứa nhiều ý đúng/sai. Lưu reference tới đoạn hoặc record cụ thể, cùng claim được kiểm tra.

~~~json
{
  "claimId": "claim-17",
  "claimTextHash": "sha256:claim-hash",
  "claimType": "ORDER_STATUS",
  "verdict": "SUPPORTED",
  "evidence": [
    {
      "sourceType": "ORDER_SYSTEM",
      "sourceRef": "order-record-opaque",
      "sourceVersion": "revision-42",
      "field": "deliveryStatus",
      "valueHash": "sha256:value-hash",
      "observedAt": "2026-11-27T12:05:00Z",
      "validAt": "2026-11-27T12:00:00Z"
    }
  ],
  "verificationMethod": "AUTHORITATIVE_RECORD_LOOKUP",
  "verifiedAt": "2026-11-27T12:06:00Z"
}
~~~

Các IDs và hashes chỉ là ví dụ. Không đưa giá trị nhạy cảm vào dataset export nếu không cần. claimTextHash giúp nối claim mà không phải lặp raw content, nhưng không thay thế evidence snapshot.

### 6.2. Evidence chain bất biến

Nếu source document hoặc business record được sửa, không ghi đè snapshot cũ. Tạo source version mới và giữ mối liên hệ tới nhãn đã dùng version trước. Khi nhãn cần thay đổi, tạo label revision hoặc revoke event có lý do; không âm thầm sửa lịch sử.

## 7. Chống feedback poisoning và thao túng nhãn

Feedback loop là một bề mặt tấn công và cũng có thể hỏng do lỗi quy trình bình thường. Dữ liệu bị thao túng có thể đi vào evaluator calibration, prompt optimization, fine-tuning, RAG memory hoặc benchmark.

### 7.1. Các tình huống cần nhận diện

- **Brigading:** nhiều tài khoản phối hợp gửi cùng một loại rating/correction.
- **Sybil-like activity:** nhiều principal mới hoặc liên quan gửi feedback để vượt quota.
- **Duplicate flooding:** gửi lại cùng payload qua nhiều request/event.
- **False correction:** người dùng đề xuất một claim sai hoặc có lợi cho họ.
- **Prompt injection in feedback:** comment chứa chỉ dẫn nhằm làm evaluator hoặc reviewer thay đổi rubric.
- **Source poisoning:** tài liệu giả được đưa vào knowledge repository hoặc vector index.
- **Self-labeling loop:** model tạo response, judge tự chấm, rồi chính verdict đó được dùng làm nhãn chuẩn.
- **Preference laundering:** thumbs up/down hoặc click được đổi tên thành correctness label.
- **Temporal poisoning:** đưa policy cũ hoặc record hết hiệu lực vào dataset hiện tại.
- **Cross-tenant contamination:** feedback hoặc evidence của tenant A bị dùng để đánh giá câu trả lời của tenant B.

OWASP GenAI Security Project xếp data/model poisoning vào các rủi ro xuyên suốt vòng đời dữ liệu, bao gồm ingestion, RAG, embeddings, memory và feedback loop. Do đó, kiểm soát cần đặt ở từng điểm tiếp nhận và biến đổi dữ liệu, không chỉ ở bước fine-tuning.

### 7.2. Rate limit và anomaly detection

Một số biện pháp:

- Giới hạn feedback theo principal, interaction, tenant và time window.
- Idempotency key cho feedback submission.
- Deduplicate theo normalized content hash và event identity.
- Theo dõi burst, duplicate ratio, source concentration và contradictory signals.
- Quarantine các batch có pattern bất thường.
- Kiểm tra verified-account policy theo domain; không xem account lâu năm là bằng chứng correctness.
- Yêu cầu source/evidence cho correction có impact cao.
- Giữ random audit trên feedback bình thường, không chỉ review event bị gắn cờ.
- Tách quyền submit feedback, verify evidence và approve golden dataset.
- Có quy trình thu hồi dataset batch khi phát hiện poisoning.

Không tự động loại mọi feedback đến dồn dập: một incident thật có thể khiến nhiều người gặp cùng lỗi. Anomaly là trigger điều tra, không phải verdict.

### 7.3. Không dùng trust score làm nhãn đúng

Có thể dùng source reliability hoặc abuse risk để ưu tiên review, nhưng không nhân trọng số rồi biến nó thành factual truth. Một nguồn có lịch sử đáng tin vẫn có thể gửi thông tin sai trong một event cụ thể. Verdict cuối cần evidence và scope của claim đó.

## 8. Ngăn vòng lặp tự xác nhận

Một failure mode nguy hiểm là dùng output của hệ thống làm ground truth cho chính hệ thống:

~~~mermaid
flowchart LR
    M["Model answer"] --> J["LLM judge"]
    J --> L["Auto label"]
    L --> D["Training / prompt dataset"]
    D --> M2["Next model or prompt"]
    M2 --> J2["Same judge family"]
    J2 --> L2["More auto labels"]
    L2 --> D2["Dataset appears self-consistent"]
~~~

Hệ thống có thể ngày càng đồng thuận với chính bias của nó trong khi độ đúng thực tế không cải thiện.

Nguyên tắc phòng tránh:

1. Tách MODEL_OUTPUT, JUDGE_VERDICT, HUMAN_LABEL và ADJUDICATED_LABEL.
2. Không promote judge verdict trực tiếp thành golden label.
3. Giữ held-out human-reviewed cases không dùng để tối ưu prompt/judge.
4. Dùng source of truth độc lập cho factual claims khi có thể.
5. Audit ngẫu nhiên các case auto-pass và auto-fail.
6. Đo judge-human agreement theo task family và rubric version.
7. Khi judge được cập nhật, chạy lại fixed anchor set và so với human labels.
8. Không để cùng một model hoặc judge tự tạo, tự chấm và tự phê duyệt dataset.

LLM evaluator vẫn hữu ích để sàng lọc, tìm case nghi vấn và đề xuất reason codes. Nó là một nguồn evidence có version, không phải một người phê duyệt độc lập.

## 9. Pipeline ingest–verify–promote

Một pipeline có thể chia thành các stage:

1. **Ingest:** nhận feedback qua API/event và gắn interaction reference.
2. **Quarantine:** giữ raw event có TTL; chưa cho phép dùng trong evaluation/gold.
3. **Normalize:** chuẩn hóa type, timestamp, locale, enum và redaction.
4. **Deduplicate:** loại event lặp theo idempotency/event identity.
5. **Validate:** kiểm tra schema, quyền truy cập, tenant scope, size và allowed fields.
6. **Triage:** phân loại preference, defect claim, factual correction, behavior hoặc abuse signal.
7. **Evidence lookup:** tải snapshot và source-of-truth có version.
8. **Automated checks:** schema/business checks và LLM evaluator nếu phù hợp.
9. **Human review:** reviewer độc lập kiểm tra claim và evidence.
10. **Adjudicate:** giải quyết bất đồng, rubric ambiguity hoặc source conflict.
11. **Promotion gate:** xác minh đầy đủ provenance, labels, approvals và dataset policy.
12. **Publish:** tạo immutable dataset version và manifest.
13. **Monitor/revoke:** audit chất lượng và thu hồi nhãn/batch khi có evidence mới.

### 9.1. Promotion gate

Một case chỉ được promote khi đáp ứng điều kiện phù hợp với dimension:

- Feedback source và acquisition channel được ghi.
- Interaction/input/response snapshot có thể truy xuất.
- Claim được diễn đạt rõ và có phạm vi.
- Evidence có source owner, version và valid time.
- Tenant/authorization scope được kiểm tra.
- Rubric và annotation protocol version được xác định.
- Người xác minh có role/expertise phù hợp.
- Bất đồng cần thiết đã được adjudicate.
- Không có unresolved abuse/poisoning flag.
- Privacy/data rights cho phép sử dụng.
- Dataset split và leakage check đã hoàn thành.
- Có approval record và provenance.

Nếu thiếu một điều kiện quan trọng, giữ ở NEEDS_EVIDENCE hoặc UNRESOLVED. Không promote để đạt quota dataset.

## 10. Ví dụ schema cho feedback và label

### 10.1. Feedback event — chưa được xác minh

~~~json
{
  "feedbackId": "fb-01JABC",
  "interactionId": "interaction-opaque-7",
  "assistantTurnId": "turn-03",
  "feedbackType": "USER_ASSERTED_CORRECTION",
  "channel": "IN_APP",
  "rating": null,
  "commentRef": "secure-comment-opaque",
  "assertedClaim": {
    "claimType": "ORDER_STATUS",
    "claimRef": "claim-17"
  },
  "sourcePrincipalRef": "principal-opaque-3",
  "tenantRef": "tenant-opaque-1",
  "receivedAt": "2026-11-27T12:05:00Z",
  "state": "QUARANTINED",
  "schemaVersion": "feedback-v3"
}
~~~

Feedback event chỉ lưu claim reference và secure comment reference. Principal/tenant references là opaque; authorization context được lấy từ server-side security principal, không tin các ID do client tự khai báo.

### 10.2. Verification record

~~~json
{
  "verificationId": "verify-01JDEF",
  "feedbackId": "fb-01JABC",
  "claimId": "claim-17",
  "verdict": "SUPPORTED",
  "verificationMethod": "SYSTEM_OF_RECORD",
  "evidenceSnapshotRef": "evidence-opaque-22",
  "sourceVersion": "order-revision-42",
  "validAt": "2026-11-27T12:00:00Z",
  "verifiedAt": "2026-11-27T12:06:00Z",
  "verifiedBy": "service-identity-opaque",
  "verificationPolicyVersion": "order-claims-v4"
}
~~~

Đây là kết quả xác minh claim, chưa phải quyết định publish dataset. Nếu claim là subjective preference hoặc không có system of record, dùng verdict phù hợp như NOT_FACTUAL, INSUFFICIENT_EVIDENCE hoặc chuyển human review.

### 10.3. Golden dataset entry

~~~json
{
  "caseId": "gold-case-00042",
  "datasetVersion": "support-golden-v12",
  "interactionSnapshotRef": "interaction-snapshot-opaque",
  "evidenceSnapshotRef": "evidence-opaque-22",
  "dimension": "FACTUALITY",
  "label": "SUPPORTED",
  "rubricVersion": "factuality-v5",
  "verificationRef": "verify-01JDEF",
  "adjudicationRef": "adj-opaque-7",
  "approval": {
    "approvedBy": "dataset-owner-opaque",
    "approvedAt": "2026-11-27T12:20:00Z"
  },
  "provenanceStatus": "COMPLETE",
  "split": "VALIDATION",
  "recordVersion": 1
}
~~~

Các ID chỉ là ví dụ. GOLDEN cần được cấp bởi promotion service sau khi kiểm tra gate; client hoặc evaluator không được gửi field này để tự nâng cấp trạng thái.

## 11. Spring Boot: tiếp nhận feedback nhưng chỉ đưa vào quarantine

Spring AI tạo response và cung cấp evaluator/observability. API feedback, quarantine store, source verification, reviewer workflow và dataset promotion là trách nhiệm của application layer.

### 11.1. DTO nhận phản hồi

~~~java
public enum FeedbackType {
    THUMBS_UP,
    THUMBS_DOWN,
    FREE_TEXT,
    USER_ASSERTED_CORRECTION,
    USER_REPORTED_DEFECT
}

public record FeedbackSubmission(
        String interactionId,
        String assistantTurnId,
        FeedbackType feedbackType,
        Integer rating,
        String comment,
        String claimReference,
        String idempotencyKey) {
}
~~~

Không nhận tenantId, userRole, verified, goldLabel hoặc approvedBy như giá trị đáng tin từ request body. Những thông tin identity, tenant và role phải lấy từ security context và authorization service.

### 11.2. Ingestion service

~~~java
@Service
public class FeedbackIngestionService {

    private final InteractionAccessPolicy accessPolicy;
    private final FeedbackRepository feedbackRepository;
    private final FeedbackOutbox outbox;
    private final FeedbackNormalizer normalizer;

    public FeedbackIngestionService(
            InteractionAccessPolicy accessPolicy,
            FeedbackRepository feedbackRepository,
            FeedbackOutbox outbox,
            FeedbackNormalizer normalizer) {
        this.accessPolicy = accessPolicy;
        this.feedbackRepository = feedbackRepository;
        this.outbox = outbox;
        this.normalizer = normalizer;
    }

    @Transactional
    public FeedbackReceipt accept(
            AuthenticatedPrincipal principal,
            FeedbackSubmission submission) {

        InteractionSnapshot snapshot =
                accessPolicy.requireReadable(
                        principal, submission.interactionId());

        NormalizedFeedback normalized =
                normalizer.validateAndRedact(submission);

        return feedbackRepository.findByIdempotencyKey(
                        principal.opaqueRef(),
                        normalized.idempotencyKey())
                .orElseGet(() -> {
                    FeedbackRecord record = FeedbackRecord.quarantined(
                            snapshot.interactionId(),
                            snapshot.tenantRef(),
                            principal.opaqueRef(),
                            normalized,
                            "feedback-policy-v3");

                    feedbackRepository.insert(record);
                    outbox.enqueueFeedbackReceived(record.id());

                    return FeedbackReceipt.quarantined(record.id());
                });
    }
}
~~~

Đây là skeleton minh họa; các domain types và repositories do ứng dụng định nghĩa. requireReadable phải xác minh người gửi có quyền phản hồi interaction đó và cùng tenant. validateAndRedact giới hạn kích thước, enum, content type và loại bỏ secrets/PII không cần thiết. Transaction + unique idempotency key ngăn duplicate event khi client retry.

Điểm quan trọng là service chỉ tạo record QUARANTINED. Không có đường đi từ request body tới GOLDEN.

### 11.3. Verification và promotion là hai quyền riêng

Verification service đối chiếu claim với evidence:

~~~java
public interface ClaimVerifier {
    VerificationResult verify(
            FeedbackRecord feedback,
            EvidenceSnapshot snapshot);
}
~~~

Promotion service kiểm tra record đã được xác minh và phê duyệt:

~~~java
@Transactional
public DatasetPromotion promote(
        FeedbackId feedbackId,
        DatasetApproval approval) {

    VerifiedFeedback verified =
            verificationRepository.requireVerified(feedbackId);

    promotionPolicy.requireEligible(verified);
    approvalPolicy.requireAuthorizedApprover(approval);
    provenanceValidator.requireComplete(verified);
    datasetRepository.insertImmutable(
            GoldenDatasetEntry.from(verified, approval));

    return DatasetPromotion.published(verified.id());
}
~~~

Đây là pseudocode cho domain boundary, không phải class có thể biên dịch độc lập. Promotion cần transaction, unique constraints và append-only/versioned records. Reviewer không tự phê duyệt case do chính họ xác minh nếu policy yêu cầu separation of duties.

## 12. Dùng Spring AI Evaluator đúng vai trò

Spring AI cung cấp Evaluator, RelevancyEvaluator và FactCheckingEvaluator. Chúng hữu ích để đánh giá response theo input và context; kết quả cần lưu như automated signal cùng model, prompt và evaluator version.

Một workflow có thể:

1. Lấy input, response và retrieved context snapshot của interaction.
2. Tạo EvaluationRequest với userText, context dưới dạng List<Content> và responseContent.
3. Chạy RelevancyEvaluator hoặc FactCheckingEvaluator phù hợp.
4. Lưu EvaluationResponse.isPass() cùng evaluator model/prompt/rubric version.
5. So sánh với verified labels trên calibration set.
6. Route disagreement hoặc insufficient evidence sang human review.

~~~java
EvaluationRequest request = new EvaluationRequest(
        interaction.userText(),
        interaction.retrievedContext(),
        interaction.responseContent());

EvaluationResponse result =
        factCheckingEvaluator.evaluate(request);

automatedSignalRepository.save(
        AutomatedSignal.from(
                interaction.id(),
                result.isPass(),
                judgeModelVersion,
                judgePromptVersion));
~~~

Đây là ví dụ theo API Spring AI 2.1.0; retrievedContext() cần cung cấp List<Content> tương ứng. isPass() là verdict của evaluator trong phạm vi context được đưa vào. Nó không xác minh source có thẩm quyền, không chứng minh context đúng và không tự cấp quyền promotion.

### 12.1. Tách fact-check signal và authoritative verification

Nếu FactCheckingEvaluator báo PASS, điều đó có nghĩa judge thấy response được context hỗ trợ theo evaluator prompt. Cần kiểm tra source context đã được xác minh hay chưa. Với claim nghiệp vụ, gọi source-of-truth adapter hoặc yêu cầu domain reviewer xác nhận.

### 12.2. Tách preference evaluation

RelevancyEvaluator không đo satisfaction; thumbs up/down cũng không thay thế relevance. Giữ các dimension riêng để tránh nhầm “người dùng thích” với “nội dung đúng”.

## 13. Kiểm soát dataset và tránh leakage

Một golden dataset có thể bị nhiễm ngay cả khi từng label riêng lẻ có vẻ hợp lý.

### 13.1. Tách các dataset theo mục đích

- **Feedback inbox:** mọi feedback mới, kể cả chưa xác minh.
- **Review queue:** case đã triage và chờ reviewer.
- **Calibration set:** case có nhãn tin cậy để hiệu chuẩn evaluator/reviewer.
- **Development set:** case được phép dùng để phát triển prompt/model.
- **Validation set:** case dùng để chọn candidate và threshold.
- **Held-out test set:** case được bảo vệ, chỉ dùng đánh giá cuối theo policy.
- **Golden regression set:** case lỗi đã xác minh, được version hóa để ngăn lỗi quay lại.

Không đồng nghĩa mọi feedback đều phải đi vào các tập này. Chỉ case đủ điều kiện mới được promote theo mục đích cụ thể.

### 13.2. Ngăn leakage giữa các split

Khi chia dataset, kiểm tra:

- Cùng conversation hoặc assistant turn không xuất hiện ở nhiều split.
- Near-duplicate prompt/response/correction không lọt qua split khác.
- Cùng document hoặc source record không làm lộ answer trong held-out test.
- Các phiên bản của một case không bị tách sang train và test.
- Feedback đã dùng để sửa prompt không xuất hiện như test case chưa từng thấy.
- Reviewer/evaluator calibration examples không bị dùng làm final test một cách âm thầm.

Có thể group split theo conversation, user/account pseudonymous group, source document, business entity hoặc time window tùy bài toán. Không dùng random row split nếu các rows có quan hệ phụ thuộc.

### 13.3. Golden benchmark phải có release version

Mỗi lần publish dataset tạo version bất biến:

- Dataset version và parent version.
- Case IDs và record versions.
- Inclusion/exclusion summary.
- Rubric và policy versions.
- Source/evidence manifest.
- Reviewer/adjudicator approvals.
- Split assignment.
- Content hash và build timestamp.
- Change log: added, corrected, revoked cases.

Không sửa trực tiếp một version đang được benchmark. Tạo version mới và giữ quan hệ lineage.

## 14. Thu hồi nhãn và xử lý khi phát hiện poisoning

Golden label không có nghĩa là không bao giờ thay đổi. Khi evidence mới chứng minh nhãn sai hoặc source bị compromise:

1. Dừng promotion của batch/dataset version liên quan.
2. Quarantine feedback records có cùng source, actor pattern, ingestion batch hoặc evidence lineage.
3. Xác định các golden cases bị ảnh hưởng bằng provenance graph.
4. Tạo REVOKED event với reason và timestamp; không xóa audit history.
5. Tạo dataset version mới loại các case không còn hợp lệ hoặc thay nhãn sau adjudication.
6. Xác định benchmark, prompt tuning, evaluator calibration hoặc model release nào đã dùng các case đó.
7. Chạy lại evaluation cần thiết và đánh dấu các kết quả cũ đã bị ảnh hưởng.
8. Sửa source validation, permissions, rate limits hoặc review protocol.
9. Thêm adversarial regression cases và theo dõi tái diễn.

Nếu một source document bị phát hiện giả, cần truy theo lineage của chunk, embedding, retrieval snapshots và evaluation cases đã dùng document đó. Chỉ xóa file hiện tại không đủ để thu hồi các bản sao đã được đưa vào dataset.

## 15. Metrics cho feedback trust pipeline

Các metric dưới đây là ví dụ do ứng dụng tự định nghĩa:

| Metric | Ý nghĩa |
| --- | --- |
| ai_feedback_received_total | Feedback events đã nhận theo type/channel |
| ai_feedback_quarantined_total | Tổng số events đã được đưa vào quarantine |
| ai_feedback_quarantine_backlog | Gauge số events hiện đang ở trạng thái quarantine |
| ai_feedback_duplicate_total | Duplicate submissions bị chặn |
| ai_feedback_rejected_total | Events bị từ chối theo reason |
| ai_feedback_triaged_total | Events đã được phân loại |
| ai_feedback_verified_total | Claims đã được kiểm tra evidence |
| ai_feedback_needs_evidence_total | Claims thiếu evidence |
| ai_feedback_adjudicated_total | Cases đã adjudicate |
| ai_feedback_promoted_total | Cases được promote vào dataset |
| ai_feedback_revoked_total | Golden labels bị thu hồi |
| ai_feedback_source_anomaly_total | Source/channel có pattern bất thường |
| ai_feedback_review_queue_age_seconds | Tuổi case chờ review |
| ai_feedback_provenance_missing_total | Case thiếu provenance bắt buộc |

Dùng labels có cardinality thấp như feedback type, channel, state, reason category, source class và dataset version đang active. Không dùng user ID, interaction ID, raw comment, document ID hoặc claim text làm metric labels.

### 15.1. Promotion rate

~~~promql
sum(rate(ai_feedback_promoted_total[1d]))
/
sum(rate(ai_feedback_received_total[1d]))
~~~

Đây là tỷ lệ promote theo event rate trong cùng cửa sổ, không phải tỷ lệ correctness. Một promotion rate thấp có thể phản ánh gate nghiêm ngặt hoặc thiếu reviewer capacity; cần xem cùng backlog và rejection reasons.

### 15.2. Quarantine backlog

~~~promql
sum(ai_feedback_quarantine_backlog)
~~~

ai_feedback_quarantined_total là counter số event đã đi vào quarantine; ai_feedback_quarantine_backlog là gauge trạng thái hiện tại. Dùng gauge để hiển thị backlog và counter để đo lưu lượng vào quarantine.

### 15.3. Provenance completeness

~~~promql
sum(rate(ai_feedback_provenance_missing_total[1h]))
/
sum(rate(ai_feedback_promoted_total[1h]))
~~~

Tỷ lệ này nên bằng 0 theo promotion policy. Nếu không có promoted cases trong cửa sổ, hiển thị không đủ dữ liệu; không chia cho 0.

### 15.4. Theo dõi source concentration

Tạo aggregate theo source class/channel và phát hiện khi một nguồn hoặc cohort chiếm tỷ trọng bất thường trong feedback/promotion. Phân tích chi tiết principal và suspected abuse trong secure analytics, không đưa định danh cá nhân vào metric labels.

## 16. Dashboard và cảnh báo

Dashboard nên có các nhóm:

| Nhóm | Nội dung |
| --- | --- |
| Intake | Received, type/channel mix, duplicate, invalid schema |
| Trust & verification | Quarantine, verified, needs evidence, rejected, source anomalies |
| Human workflow | Queue age, review throughput, adjudication/disagreement |
| Dataset promotion | Gold candidates, promoted, revoked, dataset version changes |
| Integrity | Provenance completeness, source concentration, temporal validity |
| Quality impact | Judge-human disagreement, benchmark changes, affected releases |

Cảnh báo khi:

- Feedback volume tăng bất thường hoặc một source/channel chiếm tỷ trọng đột biến.
- Duplicate/contradictory feedback tăng mạnh.
- Feedback chưa xác minh được dùng trong prompt tuning hoặc dataset build.
- Promotion xảy ra khi thiếu source snapshot hoặc approval.
- Dataset version thay đổi mà không có manifest.
- Golden label bị revoke nhưng benchmark/report cũ chưa được đánh dấu affected.
- Reviewer queue quá hạn khiến case được auto-promote để giảm backlog.
- LLM judge và human-reviewed labels bất đồng tăng theo cohort.
- Cross-tenant reference hoặc unauthorized evidence access xuất hiện.

Không cảnh báo chỉ theo raw volume. Một đợt incident thật có thể tạo feedback tăng mạnh; cần kết hợp rate, source diversity, content similarity và verified outcomes.

## 17. Quyền hạn và separation of duties

Một bảng quyền đơn giản:

| Role | Quyền |
| --- | --- |
| Feedback submitter | Gửi feedback cho interaction mà họ có quyền truy cập |
| Triage worker | Normalize, deduplicate, phân loại và route |
| Automated evaluator | Tạo automated signals có version |
| Evidence verifier | Đối chiếu claim với source/evidence |
| Human reviewer | Annotation theo rubric |
| Adjudicator | Phân xử bất đồng và ghi final reviewed label |
| Dataset approver | Phê duyệt promotion theo policy |
| Dataset publisher | Tạo immutable dataset version |
| Auditor | Đọc provenance và audit log theo quyền |

Với case high-impact, người submit, người verify và người approve nên tách biệt theo policy. Service account của evaluator không được có quyền publish golden dataset. Dataset publisher chỉ nhận các records đã qua gate.

## 18. Các lỗi thường gặp

| Lỗi | Hậu quả | Kiểm soát |
| --- | --- | --- |
| Thumbs up thành GOLD_PASS | Preference bị hiểu thành correctness | Lưu signal type riêng |
| User correction tự động thay expected answer | Claim sai hoặc malicious đi vào gold | Verify bằng source hoặc adjudication |
| LLM judge tự tạo gold label | Self-confirmation loop | Human-reviewed calibration và promotion gate |
| Lấy model output làm reference answer | Dataset học lại lỗi của model | Evidence độc lập và provenance |
| Dùng current record để chấm response cũ | Temporal label sai | Snapshot và valid time |
| Tài liệu RAG không rõ owner thành source chuẩn | Source poisoning | Source trust policy và verification |
| Duplicate feedback được đếm nhiều lần | Một actor chi phối dataset | Idempotency và dedup |
| Chỉ review case bị gắn cờ | Bỏ sót false negatives | Random audit |
| Reviewer tự approve case của mình | Conflict of interest | Separation of duties |
| Cùng conversation xuất hiện train/test | Data leakage | Group split và duplicate detection |
| Sửa nhãn tại chỗ | Mất audit history | Append-only revision và revoke event |
| Metric backlog dùng counter như gauge | Dashboard sai | Export state gauge đúng nghĩa |

## 19. Quy trình triển khai end-to-end

1. Định nghĩa feedback taxonomy: satisfaction, correction, defect, behavior và business outcome.
2. Tạo feedback API có authentication, tenant authorization và idempotency.
3. Lưu mọi submission ở trạng thái QUARANTINED.
4. Redact, normalize, validate schema và deduplicate.
5. Phân loại preference signal với factual claim.
6. Lưu interaction, prompt/model, RAG và tool snapshots bằng secure references.
7. Xác định source of truth theo domain và valid time.
8. Chạy deterministic checks và LLM evaluator như automated signals.
9. Route case cần thiết tới independent human review.
10. Adjudicate bất đồng và ghi reason/evidence.
11. Kiểm tra promotion policy, provenance, privacy, rights và dataset split.
12. Approve và publish immutable dataset version.
13. Monitor source concentration, poisoning signals, queue và promotion.
14. Audit ngẫu nhiên các case đã được auto-triage hoặc auto-verify.
15. Thu hồi labels/batches khi phát hiện source compromise hoặc verdict sai.
16. Re-run benchmark, prompt/model evaluation và release impact assessment.

## 20. Checklist kiểm thử production

| Kịch bản | Kết quả cần xác minh |
| --- | --- |
| User gửi thumbs up | Chỉ tạo satisfaction signal, không tạo golden label |
| User gửi correction | Tạo factual claim ở trạng thái quarantine |
| Client gửi approvedBy hoặc goldLabel | Server bỏ qua/từ chối field không được phép |
| Duplicate idempotency key | Không tạo feedback record thứ hai |
| User truy cập interaction tenant khác | Authorization từ chối |
| Feedback comment chứa prompt injection | Nội dung được coi là untrusted data |
| LLM judge PASS nhưng source snapshot sai | Case không được promote chỉ từ judge |
| Business record thay đổi sau interaction | Evaluation dùng snapshot/valid time phù hợp |
| Hai reviewers bất đồng | Tạo adjudication task |
| Feedback burst từ một cohort | Anomaly alert và quarantine review |
| Một source document bị thu hồi | Tìm được các cases phụ thuộc qua provenance |
| Evidence thiếu hoặc hết retention | NEEDS_EVIDENCE/UNRESOLVED, không lấy source hiện tại thay thế |
| Dataset split có near duplicates | Leakage check phát hiện |
| Golden label bị xác định sai | Tạo REVOKED event và dataset version mới |
| Reviewer tự submit và approve | Promotion policy chặn conflict of interest |
| Metric backlog | Dùng gauge trạng thái hiện tại |
| Feedback pipeline bị lỗi | Không làm hỏng response path của user |
| Dataset publish duplicate | Immutable version/idempotency ngăn publish lặp |

## 21. Bài tập thực hành

### Bài 1. Phân loại feedback

Tạo 20 feedback events gồm thumbs up/down, free text, correction, retry và business outcome. Gán mỗi event vào preference signal, factual claim hoặc behavioral signal. Giải thích loại nào không thể tự tạo correctness label.

### Bài 2. Xây feedback quarantine API

Tạo endpoint nhận feedback với authenticated principal, interaction authorization, idempotency và redaction. Xác minh mọi record mới có state QUARANTINED.

### Bài 3. Verify claim bằng source of truth

Tạo case người dùng sửa trạng thái đơn hàng. So claim với order record snapshot có revision và valid time. Lưu verification record và source reference.

### Bài 4. Human promotion gate

Tạo workflow reviewer → adjudicator → dataset approver. Kiểm tra reviewer không thể tự phê duyệt case của mình và case thiếu evidence không được promote.

### Bài 5. Phát hiện feedback poisoning

Sinh một burst feedback trùng lặp hoặc nhiều correction mâu thuẫn. Kiểm tra rate limit, dedup, anomaly signal và quarantine. Đảm bảo anomaly không tự động kết luận feedback là sai.

### Bài 6. Ngăn self-labeling loop

Tạo một LLM judge verdict và một human-adjudicated label khác nhau. Xác minh judge verdict vẫn là automated signal, không ghi đè human label hoặc trở thành gold.

### Bài 7. Dataset lineage và revoke

Publish một dataset version, sau đó phát hiện source document đã bị compromise. Tìm các cases phụ thuộc, revoke labels và tạo version mới có change log.

### Bài 8. Kiểm tra leakage

Tạo các records cùng conversation/source document và thử random row split. Sau đó dùng group split và near-duplicate detection để xác minh các records liên quan không nằm ở train và held-out test cùng lúc.

## 22. Tổng kết

Ngăn phản hồi chưa xác minh tự động trở thành đáp án chuẩn là yêu cầu về chất lượng dữ liệu và integrity của toàn bộ vòng đời AI:

- User rating, free-text, correction và behavior signals có ý nghĩa khác nhau; không tự động là correctness labels.
- Golden label phải gắn với dimension, evidence, source version, valid time, rubric và provenance.
- Feedback mới đi vào quarantine, sau đó normalize, deduplicate, triage và verify.
- LLM evaluator tạo automated signal có version; không tự phê duyệt nhãn chuẩn.
- Human review và adjudication xử lý claim khó, bất đồng và rủi ro cao.
- Promotion gate kiểm tra evidence, quyền sử dụng, separation of duties và dataset lineage.
- Chống poisoning bằng rate limit, anomaly detection, source validation, random audit và khả năng revoke.
- Giữ các dataset splits riêng; tránh leakage theo conversation, user, document, entity và thời gian.
- Dataset versions bất biến giúp tái hiện benchmark và điều tra ảnh hưởng.
- Spring AI cung cấp Evaluator; feedback workflow, evidence verification và golden dataset governance do application xây dựng.
- Khi phát hiện nhãn sai, revoke có provenance và tạo version mới thay vì sửa lịch sử âm thầm.

Một feedback event chỉ trở thành dữ liệu chuẩn khi hệ thống có thể giải thích ai gửi, họ đang khẳng định điều gì, evidence nào hỗ trợ, ai xác minh, rubric nào được áp dụng và dataset version nào đã sử dụng nó. Quy trình này giúp feedback cải thiện hệ thống mà không biến sai lầm hoặc thao túng thành chuẩn mới.

## Tài liệu tham khảo

- [OWASP GenAI Security Project — LLM05:2026 Data and Model Poisoning](https://genai.owasp.org/llm2026/llm052026-data-and-model-poisoning/): poisoning trong ingestion, RAG, embeddings, memory và feedback loops; provenance, validation, human oversight, rate limits và data versioning.
- [OWASP AI Exchange — General Controls: Limit the Effects of Unwanted Behaviour](https://owaspai.org/go/limitunwanted): feedback loops và recursive pollution khi model outputs đi vào dữ liệu của model tương lai.
- [TensorFlow Extended — TensorFlow Data Validation](https://www.tensorflow.org/tfx/guide/tfdv): schema-based validation, anomaly detection, training-serving skew và drift detection.
- [OWASP Cheat Sheet — LLM Prompt Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html): coi retrieved content, tool output và conversation history là dữ liệu không tin cậy; kiểm tra action và quyền ở application layer.
- [Spring AI Reference — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html): Evaluator, EvaluationRequest, RelevancyEvaluator và FactCheckingEvaluator.
