# Limitations of Text Indexes for Fuzzy Matching, Autocomplete, and Vietnamese in MongoDB

A product management application may store hundreds of thousands of product names, descriptions, brands, and categories in MongoDB. Users might enter `điện thoại Samsung`, `dien thoai`, `sam sung`, `samsng`, `điện`, or just type `sam` and expect autocomplete suggestions. All of these are "text search" requirements from a product perspective, yet they **are not the same technical problem**.

MongoDB provides **legacy text indexes** to power the `$text` operator. They are useful for keyword search over tokens present in documents, offering basic language options and `textScore` ranking. However, a text index is **not** an edit-distance fuzzy matcher, a character-by-character typeahead engine, or a deep Vietnamese linguistic analyzer.

This lesson in the **Text Search** chapter of the **Database Engine Document MongoDB** module explains how to evaluate three major limitations:

1. **Fuzzy search:** users mistype, omit, or add extra characters, such as `samsng` instead of `samsung`.
2. **Autocomplete / typeahead:** users enter a prefix or short fragment and expect instant suggestions.
3. **Vietnamese:** tone marks, the letter `đ`, Unicode normalization, multi-syllable compound words like `bất động sản`, and spelling variants.

Once we understand `$text` limitations, we can evaluate **B-tree indexes + prefix filters**, **normalized fields**, **MongoDB Search / Atlas Search**, or a **dedicated search engine** based on real requirements rather than forcing one technique onto every scenario.

## 1. Four Types of "Search" to Distinguish

Before choosing an index, classify what the application is asking.

| Query Type | User Input Example | Desired Semantics | Suitable Approach to Evaluate |
| --- | --- | --- | --- |
| **Exact lookup** | `SKU-IPH-15-BLK` | Match the exact product code | Equality + B-tree index |
| **Full-text keyword search** | `điện thoại samsung` | Find documents containing relevant keywords | Text index `$text` or search index |
| **Prefix / autocomplete** | `sams` | Suggest `Samsung Galaxy…` while typing | Prefix field/index or autocomplete search |
| **Fuzzy / typo tolerance** | `samsng` | Find `Samsung` despite typos | Dedicated fuzzy search |
| **Vietnamese-aware search** | `bat dong san` / `bất động sản` | Match meaning and accent/segmentation variants | Normalization + language analysis + ranking |
| **Semantic search** | `điện thoại pin trâu cho du lịch` | Match intent, not just overlapping words | Search ranking / semantic or vector search when needed |

A single API may combine multiple search types; what matters is **not equating text index capabilities with the full MongoDB Search platform**.

### Realistic Scenario

Suppose the database stores a product:

```javascript
{
  _id: "P001",
  tenantId: "shop-01",
  name: "Điện thoại Samsung Galaxy A55",
  description: "Điện thoại Android pin lâu, chụp ảnh đẹp",
  category: "phone",
  brand: "Samsung"
}
```

The application may need different behaviors:

- Search `P001`: must be exact, no fuzziness.
- Search `Samsung Galaxy`: keyword search works.
- Type `Sam`: needs prefix/autocomplete.
- Type `Samsng`: needs typo tolerance.
- Type `dien thoai`: needs a Vietnamese diacritic-handling strategy.
- Type `điện thoại pin lâu`: needs multi-word balancing, relevance, and ranking.

Creating a single text index does not automatically solve all six.

## 2. How Does a Legacy Text Index Work?

A MongoDB text index indexes **words/tokens within chosen text fields**. When running `$text`, MongoDB uses that index to find matching documents rather than scanning every document for a substring.

Example on the `products` collection:

```javascript
db.products.createIndex(
  { name: "text", description: "text" },
  {
    name: "idx_product_text",
    default_language: "none",
    weights: {
      name: 8,
      description: 2
    }
  }
);
```

Meaning:

- `name` and `description` are the text-indexed fields.
- `weights` gives keyword matches in the product name higher importance than matches in the description.
- `default_language: "none"` disables **stemming** and **stop-word filtering** from the text index's supported language list.
- `name: "idx_product_text"` is the index name, **not a searchable field name**.

### Tokens Rather Than Arbitrary Substrings

Fundamentally, a text index breaks content into tokens and builds a keyword lookup structure. It **does not store every prefix of every token** or every possible typo variant.

```text
Product name: "Samsung Galaxy A55"
                 |
                 v
          analyze / tokenize
                 |
       +---------+---------+
       |         |         |
   "samsung"  "galaxy"   "a55"
       |         |         |
       +---------+---------+
                 |
               text index
```

A query for `samsung` matches the corresponding token. However, `sams` **does not** automatically match `samsung`, nor does `samsng` automatically become `samsung`.

### When Is a Text Index Useful?

It is a reasonable starting point for applications where:

- Users enter fairly clear, complete keywords.
- Complex typo tolerance is not required.
- Instant character-by-character typeahead is not required.
- Datasets and schemas are relatively straightforward.
- Specialized Vietnamese linguistic analysis is not critical.
- A basic built-in full-text solution directly inside MongoDB queries suffices.

**Do not dismiss text indexes merely because they lack fuzziness.** They remain helpful when requirements fit; limitations appear only when product expectations exceed them.

## 3. Practice Dataset

Run the examples below only in a practice database; if the collection already exists, duplicate keys or index conflicts may occur. Use `mongosh` on an authorized MongoDB instance:

```javascript
use mongo_text_search_lab

db.products.insertMany([
  {
    _id: "P001",
    tenantId: "shop-01",
    name: "Điện thoại Samsung Galaxy A55",
    description: "Điện thoại Android pin lâu và chụp ảnh đẹp",
    brand: "Samsung",
    category: "phone"
  },
  {
    _id: "P002",
    tenantId: "shop-01",
    name: "Điện thoại iPhone 15 Pro",
    description: "Smartphone hiệu năng cao, camera chất lượng",
    brand: "Apple",
    category: "phone"
  },
  {
    _id: "P003",
    tenantId: "shop-01",
    name: "Máy ảnh Sony Alpha",
    description: "Máy ảnh kỹ thuật số cho người mới học",
    brand: "Sony",
    category: "camera"
  },
  {
    _id: "P004",
    tenantId: "shop-01",
    name: "Máy lọc không khí",
    description: "Thiết bị làm sạch không khí trong phòng",
    brand: "AirHome",
    category: "home"
  },
  {
    _id: "P005",
    tenantId: "shop-01",
    name: "Sách học máy cơ bản",
    description: "Giới thiệu học máy và trí tuệ nhân tạo",
    brand: "BookHouse",
    category: "book"
  },
  {
    _id: "P006",
    tenantId: "shop-01",
    name: "Bàn phím cơ không dây",
    description: "Bàn phím Bluetooth cho lập trình viên",
    brand: "KeyLab",
    category: "accessory"
  },
  {
    _id: "P007",
    tenantId: "shop-01",
    name: "Bún bò Huế đóng gói",
    description: "Món ăn đặc sản có vị cay",
    brand: "HueFoods",
    category: "food"
  },
  {
    _id: "P008",
    tenantId: "shop-02",
    name: "Điện thoại Samsung Galaxy S24",
    description: "Điện thoại camera tốt và màn hình lớn",
    brand: "Samsung",
    category: "phone"
  },
  {
    _id: "P009",
    tenantId: "shop-02",
    name: "Bất động sản ven sông",
    description: "Danh sách nhà ở và căn hộ",
    brand: "RealHome",
    category: "realestate"
  },
  {
    _id: "P010",
    tenantId: "shop-01",
    name: "Áo khoác chống nắng",
    description: "Quần áo dùng trong mùa hè",
    brand: "Wear",
    category: "clothing"
  }
])
```

The dataset includes multi-syllable Vietnamese words, Vietnamese diacritics, multiple tenants, and English brand names to illustrate the differences among token search, autocomplete, and fuzzy matching.

Create the legacy text index:

```javascript
db.products.createIndex(
  { name: "text", description: "text" },
  {
    name: "idx_product_text",
    default_language: "none",
    weights: { name: 10, description: 2 }
  }
)
```

## 4. What `$text` Can Do

### 4.1. Keyword Search

```javascript
db.products.find({
  $text: {
    $search: "Samsung"
  }
})
```

MongoDB searches tokens according to text index rules. Any document containing a matching token can be returned.

Multiple words:

```javascript
db.products.find({
  $text: {
    $search: "Samsung Galaxy"
  }
})
```

**Do not assume a multi-word string performs an exact ordered AND.** In `$text` syntax, unquoted search terms follow term-matching semantics (OR by default), not "must contain this exact phrase verbatim."

If the product requires all words to appear, consider **query syntax, phrase search, a search engine**, or additional predicates. Matching single words vs. matching meaningful phrases are two different tasks.

### 4.2. Phrase Search

To search for a quoted phrase in `$search`:

```javascript
db.products.find({
  $text: {
    $search: "\"Samsung Galaxy\""
  }
})
```

Phrase conditions are still governed by **tokenization, case/diacritic settings, and index language**. It is not a raw "compare literal string value" operator like field equality.

### 4.3. Excluding Terms

In text search syntax, a minus sign can exclude a term:

```javascript
db.products.find({
  $text: {
    $search: "điện thoại -iPhone"
  }
})
```

This query illustrates term/exclusion semantics. With Vietnamese text and differing tokenization behavior, **do not hardcode expectations** based purely on reading product titles; test queries on actual data.

### 4.4. Sorting by `textScore`

```javascript
db.products.find(
  {
    tenantId: "shop-01",
    $text: { $search: "Samsung Galaxy" }
  },
  {
    name: 1,
    brand: 1,
    score: { $meta: "textScore" }
  }
).sort({
  score: { $meta: "textScore" }
})
```

`textScore` is a **text-search relevance signal**, not a "90% probability the product is right"; it neither measures Levenshtein distance nor infers shopping intent.

An index assigning high weights to `name` scores name matches differently from description matches. Evaluate quality with representative queries rather than treating the score as an absolute scale comparable across datasets, indexes, or versions.

### 4.5. Configuring Language on a Query

```javascript
db.products.find({
  $text: {
    $search: "điện thoại",
    $language: "none",
    $caseSensitive: false,
    $diacriticSensitive: false
  }
})
```

These are **classic `$text` options**, not fuzzy search settings. `$language: "none"` affects stemming and stop words, but **does not turn MongoDB into a Vietnamese NLP engine**.

## 5. Fundamental Limitations of Text Indexes

| Capability | Classic Text Index / `$text` | User Impact |
| --- | --- | --- |
| Match tokens present in text | **Yes** | Complete words are easy to find |
| Phrase search via text syntax | **Limited by tokenizer** | Phrase search is not raw literal substring matching |
| Rank using `textScore` | **Yes** | Can prioritize results by term weights |
| Auto-correct `samsng` to `samsung` | **No automatic edit-distance fuzziness** | One typo can yield zero results |
| Autocomplete `sam` → `Samsung` | **Does not generate prefix tokens** | Partial words may return nothing |
| Accurate semantic Vietnamese compound splitting | **No dedicated Vietnamese linguistic analyzer** | Multi-syllable terms can mismatch |
| Domain synonyms | **Not built in** | `điện thoại` and `smartphone` are not synonyms automatically |
| Spell suggestions | **No built-in spell-suggestion feature in `$text`** | Needs an extra pipeline or engine |
| Contextual/semantic search | **Not semantic search** | Keyword matching differs from intent understanding |
| Highlighting matched spans | **No dedicated search-engine highlighter** | UI needs another solution to highlight matches |
| Rich per-field analyzer tuning | **Limited compared to search engines** | Hard to satisfy deep Vietnamese needs |

A complete search solution often combines **exact lookup**, **prefix**, **keyword**, **fuzzy**, **synonyms**, and **ranking**. There is no reason to cram all of them into a single `$text` query.

## 6. First Limitation: Fuzzy Matching and Typos

### 6.1. "Approximate Match" Means Many Different Things

In applications, "fuzzy/approximate search" might mean:

- **Typo tolerance:** `samsng` → `samsung` (missing `u`).
- **Extra character:** `samsungg` → `samsung`.
- **Transposition:** `samusng` → `samsung`.
- **Vietnamese accent differences:** `dien thoai` → `điện thoại`.
- **Spacing variations:** `sam sung` → `samsung`.
- **Abbreviations:** `dt` → `điện thoại`.
- **Synonyms:** `smartphone` → `điện thoại thông minh`.
- **Semantic similarity:** `điện thoại quay video tốt` → products with strong cameras.

These are **distinct problems**. Character *edit distance* solves only a subset; it does not generate synonyms, understand sentence intent, or fix Vietnamese syllable spacing.

### 6.2. Text Indexes Do Not Generate Single-Edit Variants

Example:

```javascript
// Actual name:
// "Điện thoại Samsung Galaxy A55"

db.products.find({
  $text: { $search: "samsng" }
})
```

If the index only holds the token `samsung`, `$text` **does not search tokens within one insertion away**. It has no option like:

```javascript
// INVALID SYNTAX for classic $text:
{
  $text: {
    $search: "samsng",
    fuzzy: { maxEdits: 1 }
  }
}
```

Never confuse a **MongoDB Search** feature example with a classic `$text` option. Both systems use different indexes and query syntax.

### 6.3. Why Adding `$regex` Does Not Fully Solve It

Someone might try:

```javascript
db.products.find({
  name: /sam.*ng/i
})
```

This regex only matches strings following `sam` then `ng`; it **does not** compute arbitrary character substitutions, insertions, or deletions. Supporting varied typos would require huge numbers of regexes—unmaintainable and resource-heavy.

Regex is **not** a spell-checking algorithm and has no edit-distance scoring integrated into classic text indexes.

## 7. What Are Edit Distance and Fuzzy Search Really?

**Levenshtein distance** is the minimum number of single-character insertions, deletions, or substitutions needed to transform string A into string B.

Examples:

```text
"samsng" -> "samsung"
      insert "u"
Edit distance = 1

"samsang" -> "samsung"
      replace "a" with "u"
Edit distance = 1
```

A fuzzy engine bounds the allowed edits (e.g., 1 or 2) alongside parameters such as:

- **prefixLength:** number of leading characters that must match exactly.
- **maxExpansions:** cap on the number of candidate variants explored.
- **tokenization:** which words/tokens fuzzy matching applies to.
- **minimum query length:** avoids running fuzzy expansion on overly short queries that produce noise.

### Fuzziness Should Not Always Be Cranked to Maximum

If a user types just `a` and the search engine allows 2 edits, huge numbers of unrelated tokens will fall within distance 2. The system will return irrelevant results and waste compute.

A practical UX strategy:

1. Prioritize **exact / keyword / prefix** matches when strong hits exist.
2. When the query is long enough and results are sparse, fall back to **fuzzy matching with bounded `maxEdits`**.
3. Score fuzzy matches lower than exact matches.
4. Apply filters for tenant, access permissions, product status, and category.
5. Measure **precision, recall, and latency**, not just result count.

### Vietnamese Is More Than Levenshtein

`điện thoại` and `dien thoai` differ in tone marks, circumflexes, and the letter `đ`. Raw Unicode code-point edit distance can exceed what users perceive as a small difference. A Vietnamese pipeline therefore usually needs to **normalize** text first before deciding whether to apply fuzzy matching.

## 8. Second Limitation: Autocomplete Is Not Full-Text Keyword Search

Autocomplete happens while the user is still typing:

```text
User types:
  "s" -> "sa" -> "sam" -> "sams" -> "samsu"

App wants to suggest:
  Samsung
  Samsung Galaxy A55
  Samsung Galaxy S24
```

In a classic text index, the token `samsung` does not generate `s`, `sa`, `sam`, `sams`, `samsu` entries. Consequently:

```javascript
db.products.find({
  $text: { $search: "sam" }
})
```

is not equivalent to "every product containing a word starting with `sam`."

### 8.1. Prefix Search on a Normalized Field

If the requirement is simply suggesting **names starting with a prefix**, you can maintain a pre-normalized field `nameNorm` on write:

```javascript
{
  _id: "P001",
  name: "Điện thoại Samsung Galaxy A55",
  nameNorm: "dien thoai samsung galaxy a55"
}
```

Create a B-tree index:

```javascript
db.products.createIndex(
  { tenantId: 1, nameNorm: 1 },
  { name: "idx_tenant_name_norm" }
)
```

When the user enters `dien t`, after normalizing, you can use an **anchored regex**:

```javascript
db.products.find({
  tenantId: "shop-01",
  nameNorm: /^dien t/
}, {
  name: 1,
  brand: 1
}).limit(10)
```

With a B-tree index and suitable predicates, a regex **starting with `^` and a literal prefix** can leverage the index much more effectively than a regex starting with `.*`. Never assume case-insensitive or collation-based regexes use indexes identically; verify with `explain()`.

### Yet Field Prefix Is Not Word-Level Autocomplete

`nameNorm: "dien thoai samsung galaxy a55"` starts with `dien`, **not `sam`**. The query:

```javascript
db.products.find({
  nameNorm: /^sam/
})
```

will **miss P001** even though `Samsung` appears in the name. This is the difference between **prefix-of-field** and **prefix-of-token**.

Possible solutions:

- Maintain a dedicated brand suggestion field.
- Store an array of normalized tokens/prefixes with deliberate index design.
- Use an **autocomplete search index** with an appropriate tokenizer.
- Use a dedicated search service if the UI must suggest matches at any word position in the name.

Never claim a field-anchored regex delivers full search-engine autocomplete.

### 8.2. Contains Search Can Be Expensive

The query:

```javascript
db.products.find({
  nameNorm: /samsung/
})
```

is an unanchored **substring search**. It generally cannot exploit a B-tree index the way equality or anchored prefixes do; on large collections it may inspect many keys or documents.

```javascript
// Especially warrants caution:
db.products.find({
  nameNorm: /.*samsung.*/i
})
```

Adding `.*` and the `i` flag does not turn the query into a full-text engine. With Unicode data and collations, actual index impact must be measured.

### 8.3. Autocomplete Is More Than a Query

A solid typeahead UI also requires:

- **Debounce:** avoid firing a request on every rapid keystroke.
- **Minimum length:** often start at 2–3 characters instead of 1.
- **Limit:** return only the top N suggestions.
- **Cancel stale requests:** discard responses from older queries once the user keeps typing.
- **Ranking:** prioritize start-of-name hits, brand matches, popularity, in-stock status, and tenant scope.
- **Authorization:** never leak suggestions from another tenant.
- **Latency budget:** typeahead needs consistent p95/p99 latency, not just good averages.

Therefore, "having a prefix index" is only part of the solution.

## 9. Third Limitation: Vietnamese Word Structure

Vietnamese separates **syllables with spaces**, yet a single word can consist of multiple syllables:

```text
"điện thoại"      -> one concept, two syllables
"bất động sản"    -> one concept, three syllables
"học máy"         -> two-syllable technical term
"thành phố"       -> two syllables
"bún bò Huế"      -> multi-component dish name
```

A whitespace-based tokenizer sees `bất`, `động`, and `sản` as three independent tokens. Term queries can then return documents containing an individual syllable that are unrelated to the full concept.

### 9.1. Syllable Splitting Differs from Word Segmentation

Example:

```text
Sentence: "Tôi đang tìm tài liệu học máy"

Split by whitespace:
  Tôi | đang | tìm | tài | liệu | học | máy

Linguistic word/term segmentation may want:
  tôi | đang | tìm | tài_liệu | học_máy
```

The underscores here merely **illustrate word segmentation**, not a required MongoDB storage format. A real Vietnamese analyzer identifies compound words, polysemous terms, proper nouns, abbreviations, and context according to its model or dictionary rules.

Classic text indexes **do not provide a specialized Vietnamese stemmer and word segmenter like a Vietnamese NLP engine**. Picking another language such as `english` will not make the text index understand Vietnamese compound words.

### 9.2. What Does `default_language: "none"` Solve?

MongoDB's classic text index applies processors for a fixed set of supported languages. Using:

```javascript
db.products.createIndex(
  { name: "text", description: "text" },
  { default_language: "none" }
)
```

tells MongoDB **not to perform language-specific stemming or stop-word removal**. This avoids applying mismatched English rules to Vietnamese content.

However, `none` **does not**:

- Segment `bất động sản` into a single lexical unit.
- Treat `điện thoại` and `smartphone` as synonyms.
- Handle every accented and unaccented variant seamlessly.
- Fix `samsng`.
- Suggest `điện` when the user types `đi`.

**It is a safeguard against wrong language transformations, not a complete Vietnamese NLP solution.**

### 9.3. Stemmers and Stop Words Risk Corrupting Domain Terms

If an index uses an inappropriate language rule set, product codes, brand names, locations, or abbreviations may be mangled unexpectedly. A catalog system often needs exact preservation of:

```text
iPhone 15
Galaxy A55
USB-C
Wi-Fi 6
Quận 1
RTX 4070
```

Tokens with digits, punctuation, or model identifiers do not always fit the same analyzer designed for ordinary prose.

## 10. Tone Marks, Unicode, and the Letter `đ`

A Vietnamese word can be represented in multiple ways at the Unicode level. Two visually identical strings can be encoded using:

- **Precomposed** characters with diacritics baked in.
- Base characters followed by **combining marks**.

For instance, `ế` can be a single precomposed code point or a sequence of combining code points. If an application normalizes inconsistently, equality/prefix matching and derived search fields can produce surprising mismatches.

### 10.1. Unicode NFC Normalization

In JavaScript:

```javascript
const a = "ế";
const b = "e\u0302\u0301";

print(a === b);  // can be false at the code-point sequence level
print(a.normalize("NFC") === b.normalize("NFC")); // true
```

`normalize("NFC")` unifies how composable diacritics are encoded. This is **different** from **stripping accents for accent-insensitive search**.

### 10.2. Stripping Diacritics to Build a Search Field

A simple application normalization helper:

```javascript
function normalizeVietnameseForSearch(input) {
  return String(input ?? "")
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .toLocaleLowerCase("vi-VN")
    .replace(/\s+/g, " ")
    .trim()
    .normalize("NFC");
}

print(normalizeVietnameseForSearch("Điện thoại"));
// "dien thoai"

print(normalizeVietnameseForSearch("Bún bò Huế"));
// "bun bo hue"
```

Explanation:

1. `NFD` decomposes many accented characters into a base character plus combining marks.
2. `\p{M}` in a Unicode-aware regular expression removes characters in the Unicode **Mark** category.
3. `đ` and `Đ` **do not decompose into d/D under NFD alone**, so they are mapped explicitly.
4. `toLocaleLowerCase("vi-VN")` lowercases the string per locale where supported by the JavaScript runtime.
5. Whitespace collapse and `NFC` produce a stable representation.

This is a **search-helper function**, not a universal linguistic standard for every app. It erases meaningful distinctions:

```text
"ma" vs "má" vs "mà" vs "mã"
"ban" vs "bán" vs "bàn" vs "bạn"
"do" vs "đo"
```

Therefore, always **keep the original field** for display and exact lookup; the accent-stripped field is strictly a **search-support variant**.

### 10.3. Text Indexes and Diacritic Sensitivity

Classic `$text` provides `$diacriticSensitive`, and modern text index versions default to diacritic-insensitive matching. Yet "diacritic-insensitive" inside the text index **is not equivalent** to business-grade Vietnamese normalization:

- Tokenization may still fail to match compound words.
- `đ`/`d` and Unicode forms must be tested in practice.
- Unaccented queries can over-match or behave unexpectedly.
- Exact accented matches often deserve higher rank than accent-folded hits.

Do not assume `$diacriticSensitive: false` alone delivers high-quality Vietnamese search.

## 11. Designing Original Fields Alongside Normalized Fields

A schema can store both the original text and its normalized key:

```javascript
{
  _id: "P001",
  tenantId: "shop-01",
  name: "Điện thoại Samsung Galaxy A55",
  nameNorm: "dien thoai samsung galaxy a55",
  brand: "Samsung",
  brandNorm: "samsung",
  description: "Điện thoại Android pin lâu và chụp ảnh đẹp"
}
```

Key points:

- `name` is the display source and canonical value; never overwrite it with unaccented text.
- `nameNorm` serves prefix/equality/range queries under the chosen normalization policy.
- `brandNorm` can power brand autocomplete from the start of the string.
- Normalized values must use the **exact same algorithm at both index-time and query-time**.
- Whenever `name` or `brand` changes, update both original and normalized fields together.

### Updating Sample Data with Normalized Fields

To practice in `mongosh`, populate normalized fields on the lab collection:

```javascript
function normalizeVietnameseForSearch(input) {
  return String(input ?? "")
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .toLocaleLowerCase("vi-VN")
    .replace(/\s+/g, " ")
    .trim()
    .normalize("NFC");
}

db.products.find({}, { _id: 1, name: 1, brand: 1 }).forEach(p => {
  db.products.updateOne(
    { _id: p._id },
    {
      $set: {
        nameNorm: normalizeVietnameseForSearch(p.name),
        brandNorm: normalizeVietnameseForSearch(p.brand)
      }
    }
  );
});
```

This is a backfill on the **lab collection**. Never run an uncontrolled `find().forEach(updateOne)` loop over millions of production documents; large systems need batched migrations, resumability, and load monitoring.

Create indexes:

```javascript
db.products.createIndex(
  { tenantId: 1, nameNorm: 1 },
  { name: "idx_tenant_nameNorm" }
)

db.products.createIndex(
  { tenantId: 1, brandNorm: 1 },
  { name: "idx_tenant_brandNorm" }
)
```

### Using Prefix Search on the Normalized Field

```javascript
const rawInput = "Điện t";
const normalized = normalizeVietnameseForSearch(rawInput);

// In this lab example, normalized is known to be "dien t".
db.products.find({
  tenantId: "shop-01",
  nameNorm: /^dien t/
}, {
  name: 1, brand: 1, _id: 1
}).limit(10)
```

In production applications, **never interpolate raw user input directly into a regex** without escaping metacharacters, enforcing length bounds, and restricting to literal prefixes. The example above uses a regex literal to clearly separate regex syntax from user data.

### Prefix Search Does Not Replace Fuzzy Search

`nameNorm` lets `dien` match `Điện…` after normalization, yet `dnien` still will not match `dien`. When users mistype characters, a prefix index alone cannot recover; fuzzy search or spelling suggestions are needed.

## 12. Avoiding `$regex` Abuse for Vietnamese

A system might try to support "contains anywhere":

```javascript
db.products.find({
  nameNorm: /thoai/
})
```

Because this query has no anchored prefix at the start of the field, it does not gain the same B-tree advantage as:

```javascript
db.products.find({
  nameNorm: /^dien/
})
```

At scale, heavy contains-regex traffic can impose substantial load. In addition:

- Short substrings match inside unrelated words, producing noisy results.
- There is no lexical relevance ranking like a search engine.
- There is no real typo tolerance.
- User-controlled regexes risk excessive CPU consumption if arbitrary complex patterns are passed through.
- Tenant and access-control filtering remains mandatory.

### Regex Injection and Input Validation

Avoid:

```javascript
// Inappropriate: userInput is passed directly as a regex pattern.
db.products.find({
  nameNorm: { $regex: userInput, $options: "i" }
})
```

Instead:

1. Normalize the input string.
2. Cap input length and request rate.
3. Escape special regex characters when building literal prefixes.
4. Anchor with `^` for prefix-of-field queries.
5. Keep collation/index consistent with the normalized field.
6. Apply a reasonable `limit` and inspect `explain("executionStats")`.

### A Literal Regex Escape Helper

```javascript
// Escape characters with special meaning in JS regexes.
function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

const norm = normalizeVietnameseForSearch("Điện t");
const safePrefix = "^" + escapeRegExp(norm);

db.products.find({
  tenantId: "shop-01",
  nameNorm: { $regex: safePrefix }
}).limit(10);
```

This regex omits `i` because `nameNorm` is already lowercased. **Do not assume every dynamically constructed regex uses an index**; index optimization depends on pattern shape, engine, collation, and query plan.

## 13. Architectural Limits of a Classic Text Index

Beyond lacking fuzziness and autocomplete, classic text indexes carry structural constraints:

### 13.1. One Text Index per Collection

MongoDB allows **one classic text index per collection**, though that single index can span multiple text fields.

```javascript
db.products.createIndex(
  { name: "text", description: "text", brand: "text" },
  {
    name: "idx_all_text",
    weights: {
      name: 10,
      brand: 8,
      description: 2
    },
    default_language: "none"
  }
)
```

This example illustrates a **replacement design** for the earlier index, **not a command to run alongside an existing text index**. Running another `createIndex` with `"text"` on the same collection will fail because MongoDB forbids a second independent text index.

While a multi-field text index covers multiple fields, if you need distinct analyzers or specialized tokenization for brand names versus descriptions, the classic mechanism is far less flexible than a dedicated search index.

### 13.2. Compound Text Indexes Have Specific Rules

Regular fields and text fields can be combined in certain compound indexes, subject to strict rules on field order, field types, and mandatory equality predicates on non-text prefix keys. Do not treat a compound text index like a plain B-tree index where keys can be ordered freely.

Design illustration only:

```javascript
db.products.createIndex(
  { tenantId: 1, name: "text", description: "text" },
  { default_language: "none" }
)
```

With a leading `tenantId` prefix, `$text` queries must include an equality condition on `tenantId` to use the index properly. This fits multi-tenant apps where every query has a tenant context, but may not fit global catalog-wide search reports.

### 13.3. Not Equivalent to a MongoDB Search Index

A classic text index is created with:

```javascript
db.products.createIndex({ name: "text" })
```

MongoDB Search uses a **separate search index and search stage**, such as `$search` on supported deployments. The two index types **are not interchangeable**:

- `$text` requires a classic text index.
- `$search` requires a search index and supported search infrastructure.
- Creating a classic text index **does not** enable `$search.autocomplete`.
- Creating a search index **does not** add fuzzy matching to `$text`.

Confirm this distinction early during design.

## 14. What Does MongoDB Search / Atlas Search Solve?

On MongoDB deployments supporting **MongoDB Search** (commonly known as **Atlas Search** in MongoDB Atlas), you can define dedicated **search indexes** and use the `$search` aggregation stage for text ranking, autocomplete, and fuzzy matching.

**Do not assume `$search` runs on every standalone or self-managed replica set.** Availability, index syntax, and limits depend on server version and search service deployment. A supported search deployment is required.

### 14.1. Fuzzy Text Search with `$search`

Illustrative example on a cluster with a search index named `product_search` properly mapping `name`:

```javascript
db.products.aggregate([
  {
    $search: {
      index: "product_search",
      text: {
        query: "samsng",
        path: "name",
        fuzzy: {
          maxEdits: 1,
          prefixLength: 1,
          maxExpansions: 50
        }
      }
    }
  },
  {
    $match: {
      tenantId: "shop-01"
    }
  },
  {
    $project: {
      _id: 1,
      name: 1,
      brand: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $limit: 10 }
])
```

Meaning:

- `text` is a search operator **distinct** from classic `$text`.
- `fuzzy.maxEdits` bounds the number of edits on tokens produced by the search analyzer.
- `prefixLength` shrinks the expansion space by requiring leading characters to match exactly.
- `maxExpansions` caps how many candidate variants the search engine evaluates.
- `searchScore` is MongoDB Search's ranking score, not classic `textScore`.

**Important consideration:** Filtering by tenant in a `$match` after `$search` works functionally, but filtering early **inside `$search.compound.filter`** with proper field mapping can improve performance and narrow search scope. Never place `$limit` before access-control filters and assume you still get 10 valid results for the tenant.

### 14.2. Single-Token Fuzziness Does Not Solve All of Vietnamese

For `samsng` → `samsung`, edit-distance fuzzy matching works well. However, for:

```text
"bat dong san" <-> "bất động sản"
"sams ung"     <-> "samsung"
"dien thoai"   <-> "smartphone"
```

these pairs may require:

- **Accent folding**.
- **Word segmentation** and whitespace handling.
- **Domain synonym dictionaries**.
- **Query rewriting**.
- Intent-aware ranking.

Fuzzy matching alone does not solve these. Overly broad fuzziness on Vietnamese can actually cause short syllables to collide, generating false positives.

## 15. MongoDB Search Autocomplete

MongoDB Search provides the **`autocomplete`** operator to suggest matches as users type parts of one or more tokens, backed by an appropriately configured search index.

**Conceptual mapping example** for `name` in a search index:

```json
{
  "mappings": {
    "dynamic": false,
    "fields": {
      "name": [
        {
          "type": "autocomplete",
          "tokenization": "edgeGram",
          "minGrams": 2,
          "maxGrams": 15,
          "foldDiacritics": true
        },
        {
          "type": "string"
        }
      ]
    }
  }
}
```

This is a **search index mapping example** for MongoDB Search environments supporting these options; it is not `createIndex({name:"text"})` syntax. Verify exact configuration against your deployment and version. Mapping a field as both `autocomplete` and `string` helps when the same field serves both typeahead and full-text search.

### 15.1. Autocomplete Query

```javascript
db.products.aggregate([
  {
    $search: {
      index: "product_autocomplete",
      autocomplete: {
        query: "sam",
        path: "name",
        tokenOrder: "sequential",
        fuzzy: {
          maxEdits: 1
        }
      }
    }
  },
  {
    $project: {
      name: 1,
      brand: 1,
      score: { $meta: "searchScore" }
    }
  },
  { $limit: 10 }
])
```

When the data contains `Samsung Galaxy A55`, querying `sam` can match via a properly configured autocomplete index. Still, **quality depends on tokenization, analyzer, field mapping, `tokenOrder`, and data**—simply adding the operator does not guarantee good suggestions.

### 15.2. How Do Edge N-Grams Work?

For the token `samsung` with a minimum length of 2 characters:

```text
Original token: samsung
Prefixes that can be indexed:
  sa
  sam
  sams
  samsu
  samsun
  samsung
```

This is a **conceptual illustration**, not an exact token dump for every analyzer. `minGrams`/`maxGrams`, tokenization mode, and analyzer configuration determine the actual indexed tokens.

### 15.3. Autocomplete Trade-Offs

- Increases the number of indexed tokens, raising storage and indexing cost.
- Very short strings can match too many suggestions.
- Index-time and search-time analyzers must align.
- Sequential token matching vs. mid-string matching may call for different strategies.
- Ranking should prefer exact brand/term matches and popular items over distant fuzzy hits.
- Measure latency under concurrent continuous typing.

If you only need prefixes of SKUs or the very beginning of product names, a B-tree index can be simpler. If you need prefix matching on **any token in the phrase**, typo tolerance, and relevance ranking, a dedicated search index is worth evaluating.

## 16. Vietnamese with MongoDB Search: Analyzers Are Still Essential

MongoDB Search offers far more flexible analyzers and tokenizers than classic text indexes, yet **that does not mean every deployment automatically includes an optimal domain-specific Vietnamese word segmenter**.

A common strategy prepares:

1. **Original text:** for display, preserving diacritics and punctuation.
2. **NFC text:** consistent Unicode representation.
3. **Normalized unaccented text:** to support accent-free queries.
4. **Word-segmented text:** if Vietnamese compound words must be understood.
5. **Synonyms/aliases field:** domain pairs like `điện thoại`, `smartphone`, `đt`.

Example of a search-ready document:

```javascript
{
  _id: "P005",
  name: "Sách học máy cơ bản",
  nameNorm: "sach hoc may co ban",
  searchTerms: [
    "sách học máy",
    "học máy",
    "machine learning",
    "ml"
  ],
  category: "book"
}
```

You do not always have to store all of these fields in the source collection if your search pipeline performs equivalent analysis at index time. However, when the application needs full control over normalization or segmentation, storing derived representations makes behavior reproducible.

### 16.1. Same Algorithm at Index-Time and Query-Time

If the index stores `dien thoai` while queries still send `Điện thoại` without matching analyzer/normalization rules, effectiveness depends entirely on whether the search engine folds them identically.

A simple contract:

```text
INGEST:
    rawName
      -> Unicode NFC
      -> lowercase / fold accents
      -> tokenize / segment if needed
      -> index searchable fields

QUERY:
    rawQuery
      -> exact same normalization policy
      -> tokenize / segment if needed
      -> query the corresponding searchable fields
```

If ingest and query pipelines diverge—especially after upgrading a Vietnamese tokenizer—results can drop or skew. Changing segmentation policies typically requires a controlled **reindex/backfill** and before/after quality evaluation.

### 16.2. Compound Words and Synonyms

Example:

```text
User enters: "laptop học sinh"
Product says: "máy tính xách tay dành cho học tập"
```

Although both phrases are semantically related, a classic text index or 1–2 edit fuzzy search **will likely miss** because few raw tokens overlap. Synonym dictionaries, query rewriting, or semantic retrieval are required.

For Vietnamese, synonym pairs might include:

```text
điện thoại  <-> smartphone
máy tính xách tay <-> laptop
điều hòa <-> máy lạnh
xe máy <-> mô tô (context-dependent)
```

Not every pair is universally equivalent across all domains. Synonyms must be **curated per domain** to avoid irrelevant matches.

### 16.3. Vietnamese Has Spaces Between Syllables

Autocomplete may handle single tokens well yet struggle when users type:

```text
"bat d..."   -> "bất động sản"
"dien th..." -> "điện thoại"
```

For a smooth experience, verify how the analyzer handles multi-syllable strings and partially typed queries. Never test solely with English brand words like `samsung` and declare Vietnamese autocomplete complete.

## 17. Comparing Four Technical Strategies

| Strategy | Strengths | Weaknesses | When to Choose |
| --- | --- | --- | --- |
| **Equality / B-tree** | IDs, SKUs, structured prefixes | No true full-text or fuzziness | Exact lookup, product codes, simple prefix suggestions |
| **Classic text index + `$text`** | Keyword search, phrases/exclusions, basic scoring | No typos, autocomplete, or Vietnamese NLP | Simple search with modest requirements |
| **Normalized field + prefix/alias** | Full control over accents, abbreviations, prefixes; easy to implement | Must sync fields; hard to scale ranking/broad fuzziness | Small/medium catalogs, controlled autocomplete |
| **MongoDB Search / Atlas Search** | Fuzzy, autocomplete, advanced analyzers/ranking | Requires supported deployment/index, tuning, and cost | Rich product search / UX quality requirements |
| **Dedicated external search engine** | Mature analyzer ecosystems, synonyms, typos, search analytics | Data sync overhead, operations, latency/consistency | Systems needing specialized features or existing infra |

No option is free. Dedicated search indexes often synchronize asynchronously from the primary database, meaning newly written documents may not appear immediately in search results. **Read-after-write search visibility** requirements must be measured and designed explicitly.

### Incremental Evolution Path

```text
Stage 1:
  exact lookup + text index
          |
          v
Add normalization:
  Unicode NFC, unaccented fields, tenant filtering
          |
          v
Add autocomplete:
  prefix field or MongoDB Search autocomplete
          |
          v
Add fuzziness:
  typo tolerance + ranking exact > fuzzy
          |
          v
Enhance Vietnamese:
  segmentation, synonyms, evaluation set
```

An application can stop at Stage 1 or 2 if actual KPIs are met. Do not add fuzziness or semantic search just because the technology exists.

## 18. Multi-Tenant Search: Right Results Must Still Respect Permissions

In the sample dataset, both `shop-01` and `shop-02` carry Samsung phones. A query:

```javascript
db.products.find({
  $text: { $search: "Samsung" }
})
```

can return products across **multiple tenants**. In a multi-tenant application, that is a data security breach.

Proper query:

```javascript
db.products.find({
  tenantId: "shop-01",
  $text: { $search: "Samsung" }
})
```

With MongoDB Search, place **tenant and permission filters directly inside the search stage whenever possible**, rather than filtering after taking a global top-N `$limit`.

### Bug When Filtering After `$limit`

```javascript
// Flawed when the global top 10 spans multiple tenants:
db.products.aggregate([
  { $search: { /* search entire catalog */ } },
  { $limit: 10 },
  { $match: { tenantId: "shop-01" } }
])
```

If only two of the global top 10 belong to `shop-01`, the UI shows just two hits even if many more valid `shop-01` products ranked below position 10. Moreover, the search scope was never narrowed early.

Every layer—exact, prefix, fuzzy, and autocomplete—requires an **authenticated security context**, tenant scoping, and valid ranking rules. Fast queries that leak another tenant's names or descriptions are broken designs.

## 19. Ranking Choices for Vietnamese

Suppose a user types `dien thoai samsung` and three kinds of matches exist:

1. Products containing the phrase `Điện thoại Samsung` in the title.
2. Products mentioning `Samsung` only in the description.
3. Other products matching loosely via fuzziness or normalization.

A sample ranking hierarchy:

```text
Exact phrase/title match           high priority
Exact word/title match             high priority
Accent-insensitive normalized hit  next priority
Prefix/autocomplete hit            UI-based priority
Fuzzy typo match                   lower than exact
Synonym expansion                  domain-specific
Popularity / inventory / recency   additional signals
```

This is an **illustrative ordering**, not weights applied automatically by MongoDB. Production systems should specify desired ranking rules and validate them against real user queries.

### Accented Matches Should Outrank Unaccented Hits When Appropriate

If a user types `bán`, words like `bàn`, `ban`, and `bạn` all collide after accent stripping. Searching solely against `nameNorm` loses that distinction. You can prioritize:

- Exact accented string matches.
- Keyword matches after Unicode normalization.
- Accent-folded matches when stronger hits are scarce.

For person names, locations, legal terms, or technical codes, aggressive accent stripping can destroy precision. Provide explicit control over the **recall** vs. **precision** trade-off rather than blindly stripping accents everywhere.

## 20. Highlighting and Snippets: Avoid Naive String Concatenation

A search UI often wants to bold the matched portion:

```text
User: "samsung"
Display: "Điện thoại [Samsung] Galaxy A55"
```

Classic `textScore` returns only a number; it **does not return semantic highlight spans**. If the frontend runs naive substring matching on the title to highlight text, it breaks when:

- The query is unaccented while the title is accented.
- The match came from a synonym or typo.
- The match occurred in `description` rather than `name`.
- Unicode normalization shifts code-point offsets.
- HTML is rendered without proper escaping, causing layout bugs or injection risks.

MongoDB Search supports highlighting on compatible deployments and index mappings, subject to engine limits and APIs. If you build custom highlighting, **never render raw user input as unescaped HTML**; keep original text, matched tokens, and rendered markup cleanly separated.

## 21. Reading `explain()` and Measuring Performance

### 21.1. Classic `$text`

```javascript
db.products.find({
  tenantId: "shop-01",
  $text: { $search: "Samsung" }
}).explain("executionStats")
```

Inspect:

- Did the query use the expected text index?
- How many keys and docs were examined?
- Was the tenant predicate applied efficiently?
- Did scoring or sorting add extra overhead?
- Do larger datasets or mixed languages change selectivity?

### 21.2. Prefix B-Tree

```javascript
db.products.find({
  tenantId: "shop-01",
  nameNorm: /^dien/
}).explain("executionStats")
```

Compared to contains:

```javascript
db.products.find({
  tenantId: "shop-01",
  nameNorm: /dien/
}).explain("executionStats")
```

Inspect index usage, examined keys/docs, and timing on a **representative dataset**. A 10-document lab proves nothing about scale.

### 21.3. MongoDB Search

For `$search`, inspect **search explain/metrics** supported by your version and infrastructure, and measure end-to-end latency:

- Index build/update lag.
- Search stage execution time.
- Query expansion / fuzzy expansion cost.
- Filter selectivity.
- Documents returned and downstream pipeline stages.
- p50/p95/p99 under concurrent load.

**Never compare single-run millisecond timings.** Warm caches, freshly built indexes, concurrency, result counts, and search backend resources can all skew a single measurement.

## 22. Designing a Two-Stage Search API

An architecture can separate the **suggest API** from the **search results API**:

```text
User types:
  "s" -> "sa" -> "sam"
          |
          v
  /search/suggest?q=sam
   - prefix / autocomplete index
   - min length
   - tenant filter
   - limit 5-10
          |
          v
   Short suggestions (brand/product)

User presses Enter:
          |
          v
  /search?q=samsng
   - exact keyword
   - fuzzy fallback if needed
   - category/tenant filters
   - full result ranking
          |
          v
  Paginated result list
```

Benefits of separating both APIs:

- Suggest prioritizes **low latency** and compact results.
- Full search prioritizes **recall, relevance, and pagination**.
- Avoids running heavy fuzzy expansions on the very first keystrokes.
- Enables distinct timeouts and monitoring per endpoint.

A search solution is more than a MongoDB query; the **API contract** and behavior for short, empty, or misspelled inputs must also be defined.

## 23. Java MongoDB Sync Driver: Classic Text Index and Query

The example below uses the MongoDB Java Sync Driver to run a tenant-scoped classic text search; the project requires the `mongodb-driver-sync` dependency and the `MONGODB_URI` environment variable.

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

public class VietnameseTextSearchDemo {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db =
                client.getDatabase("mongo_text_search_lab");
            MongoCollection<Document> products =
                db.getCollection("products");

            String tenantId = "shop-01";
            String keyword = "Samsung Galaxy";

            Bson filter = Filters.and(
                Filters.eq("tenantId", tenantId),
                Filters.text(keyword)
            );

            Document projection = new Document("name", 1)
                .append("brand", 1)
                .append("score",
                    new Document("$meta", "textScore"));

            Document sort = new Document(
                "score", new Document("$meta", "textScore"));

            for (Document product : products.find(filter)
                    .projection(projection)
                    .sort(sort)
                    .limit(10)) {
                System.out.println(product.toJson());
            }
        }
    }
}
```

This snippet assumes the text index already exists. If the collection **lacks a valid text index**, the server returns an error for `$text`. Calling `Filters.text()` does not create an index automatically.

### Empty Results for `samsng` Are Not a Driver Bug

If you change:

```java
String keyword = "samsng";
```

and text search returns nothing, that is a **limitation of text token matching**, not a Java encoding or connection bug.

Do not write a loop that mutates characters in the keyword and fires hundreds of `$text` queries to fake fuzzy search. That approach wrecks load control and result quality; use an engine or pipeline built for fuzziness instead.

## 24. Java: Normalizing Vietnamese at Ingest and Query Time

Java provides Unicode normalization via `java.text.Normalizer`:

```java
import java.text.Normalizer;
import java.util.Locale;

public class VietnameseSearchNormalize {
    public static String normalize(String input) {
        if (input == null) {
            return "";
        }

        String decomposed = Normalizer.normalize(
            input, Normalizer.Form.NFD);

        String noMarks =
            decomposed.replaceAll("\\p{M}+", "");

        String noSpecialD = noMarks
            .replace('đ', 'd')
            .replace('Đ', 'D');

        String lower =
            noSpecialD.toLowerCase(Locale.forLanguageTag("vi-VN"));

        String collapsed = lower
            .replaceAll("\\s+", " ")
            .trim();

        return Normalizer.normalize(
            collapsed, Normalizer.Form.NFC);
    }

    public static void main(String[] args) {
        System.out.println(normalize("Điện thoại"));
        // dien thoai

        System.out.println(normalize("Bất động sản"));
        // bat dong san
    }
}
```

The Java and JavaScript functions above must remain **behaviorally identical** if multiple services in the same system read and write `nameNorm`. Share unit tests across both for cases like:

```text
"Điện thoại"        -> "dien thoai"
"ĐIỆN THOẠI"        -> "dien thoai"
"Bún bò Huế"        -> "bun bo hue"
"Máy học"           -> "may hoc"
"  Điện   thoại  "  -> "dien thoai"
```

Remember that accent-stripping loses information; use it only for **searchable fields**, never overwriting the original `name`.

### Safe Java Prefix Search

Simple example:

```java
import com.mongodb.client.model.Filters;
import org.bson.conversions.Bson;
import java.util.regex.Pattern;

String userInput = "Điện t";
String normalized =
    VietnameseSearchNormalize.normalize(userInput);

String safePrefix =
    "^" + Pattern.quote(normalized);

Bson filter = Filters.and(
    Filters.eq("tenantId", "shop-01"),
    Filters.regex("nameNorm", safePrefix)
);
```

`Pattern.quote()` protects the query from interpreting user input as regex syntax. However, **escaped `\Q...\E` syntax may not be recognized by the MongoDB optimizer as a literal prefix for optimal index bounds across all versions**, so always verify with `explain()`. Where efficient prefix indexing is critical, use a verified metacharacter-escaping helper or a dedicated search strategy.

Never assume `Filters.regex()` always uses an index or scales to high search volumes.

## 25. Java: Calling MongoDB Search via Aggregation

When the cluster has a `product_search` search index, Java can build the BSON pipeline:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.Arrays;
import java.util.List;

public class MongoDbSearchFuzzyExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db =
                client.getDatabase("mongo_text_search_lab");
            MongoCollection<Document> products =
                db.getCollection("products");

            Document fuzzy = new Document("maxEdits", 1)
                .append("prefixLength", 1)
                .append("maxExpansions", 50);

            Document textSearch = new Document("query", "samsng")
                .append("path", "name")
                .append("fuzzy", fuzzy);

            Document searchStage = new Document("$search",
                new Document("index", "product_search")
                    .append("text", textSearch));

            Document tenantFilter = new Document("$match",
                new Document("tenantId", "shop-01"));

            Document projection = new Document("$project",
                new Document("name", 1)
                    .append("brand", 1)
                    .append("score",
                        new Document("$meta", "searchScore")));

            List<Document> pipeline = Arrays.asList(
                searchStage,
                tenantFilter,
                projection,
                new Document("$limit", 10)
            );

            for (Document product : products.aggregate(pipeline)) {
                System.out.println(product.toJson());
            }
        }
    }
}
```

This is an **example for a supported MongoDB Search deployment**, not code that runs against a classic text index. In multi-tenant, high-volume systems, push the tenant filter into `$search.compound.filter` with appropriate mapping rather than searching globally and filtering afterward.

## 26. When Should You Use a Dedicated Search Engine?

MongoDB Search satisfies many needs within the MongoDB ecosystem, yet some situations call for a separate search service:

- The organization already operates a dedicated search engine with a battle-tested Vietnamese analyzer.
- The system needs advanced **spell correction**, **synonym management**, **custom tokenization**, **highlighting**, and sophisticated ranking strategies.
- Query volume and latency demand complete compute isolation from the transactional database.
- A dedicated **indexing pipeline** must unify documents from multiple sources beyond MongoDB.
- Specialized search analytics, click feedback, learning-to-rank, or query suggestions are required.

In return, the system must handle **data synchronization** from MongoDB to the search engine, indexing lag, retries, missing/deleted documents, idempotency, replay, and consistency.

Architecture diagram:

```text
       Application writes
             |
             v
       MongoDB products
             |
        Change Stream /
        Outbox / Queue
             |
             v
       Indexing Service
          /      \
   normalize    segment
          \      /
             |
             v
        Search Index
             |
         Search API
             |
             v
           User
```

If using Change Streams, manage checkpoints/resume tokens and handle expired oplog history. An external search service is never exempt from **exactly-once, backfill, and deletion sync** challenges.

## 27. Search Quality Evaluation Criteria

Never judge quality by "I typed a few words and saw a product."

Build a **query set** covering representative cases:

| Category | Query Example | Expectation |
| --- | --- | --- |
| Exact accented terms | `điện thoại samsung` | Samsung phones rank at the top |
| Unaccented | `dien thoai samsung` | Results remain relevant |
| Typo | `samsng galaxy` | Fuzzy matching finds the product |
| Start-of-name prefix | `dien th` | Suggests matching product names |
| Mid-name prefix | `sam` | Suggests Samsung in name/brand fields |
| Compound word | `bất động sản` | Prioritizes the intended concept |
| Abbreviation | `dt samsung` | Matches if domain defines aliases |
| Synonym | `smartphone` | Can return phones via synonyms |
| Easily confused tones | `ban` / `bàn` / `bán` | Avoids over-broad matches when precision matters |
| Exact code | `SKU-IPH-15-BLK` | Returns exact SKU without fuzzy distortion |
| Tenant isolation | `shop-02` product for `shop-01` user | Never appears |
| Very short query | `a` | Clear suggestion policy, bounded results |
| Empty query | `" "` | Never accidentally scans the whole catalog |
| Mixed Unicode forms | NFC vs. decomposed accents | Consistent behavior |

### Meaningful Metrics

- **Recall@K:** how many relevant targets appear in the top K results?
- **Precision@K:** proportion of relevant results within top K.
- **MRR / NDCG:** evaluates position of relevant results when graded labels exist.
- **Zero-result rate:** share of queries returning nothing.
- **Typo recovery rate:** share of misspelled queries still finding the intended product.
- **Suggestion acceptance rate:** share of autocomplete suggestions clicked by users.
- **p50/p95/p99 latency:** especially critical for typeahead.
- **Resource / storage cost:** search index size, CPU/RAM/I/O.
- **Freshness:** delay from product creation to search visibility.
- **Security leakage rate:** must strictly equal 0 per access policy.

Treat this as a reference metric suite; product teams should define **K**, relevance labeling guidelines, and query weights before benchmarking.

## 28. Fair Benchmarking Across Approaches

To compare classic `$text`, prefix indexes, and MongoDB Search fairly:

1. Use the **same logical collection** or identical product dataset.
2. Ensure all indexes are built and warm/stable before measuring.
3. Run the same query set spanning common and hard queries.
4. Segment results by **exact, keyword, autocomplete, typo, unaccented, and synonyms**.
5. Measure both result quality **and latency**; returning wrong products fast is not success.
6. Test concurrency, cold vs. warm cache, and update/search-index refresh lag.
7. Track index/storage overhead and write amplification during catalog updates.
8. Record MongoDB version, driver version, search deployment, and analyzer configuration.

### Sample Decision Matrix

| Criterion | Classic `$text` | Prefix `nameNorm` | MongoDB Search |
| --- | --- | --- | --- |
| Keyword search | Good for basics | Limited | Yes |
| Name prefix | Not built in | Yes, with matching index | Yes, with autocomplete |
| Mid-name / token prefix | No | No if field-prefix only | Supported via analyzer/tokenization |
| Typo `samsng` | No | No | Yes, with fuzzy |
| Unaccented Vietnamese | Depends on text index behavior | Explicit via custom normalization | Configurable via analyzer / normalized field |
| Vietnamese word segmentation | Not specialized | Must build yourself | Depends on custom preprocessing / analyzer |
| Rich ranking | Limited | Usually manual | More flexible |
| Operational complexity | Low | Medium (field sync) | Higher (search index, tuning) |
| Query latency | Must measure | Must measure | Must measure |
| Search freshness | Tied to MongoDB data index | Tied to normalized field updates | Can have search indexing lag |

**Never label any column "always faster"** without measurements from a concrete workload.

## 29. Common Implementation Pitfalls

| Symptom | Possible Cause | Remedy |
| --- | --- | --- |
| `$text` fails with no index error | Collection lacks a text index | Create a valid text index; verify name/fields |
| Searching `sam` misses Samsung | Classic text index does not generate prefixes | Use prefix field or autocomplete index |
| Searching `samsng` misses Samsung | No fuzzy edit distance | Use search engine fuzziness / query correction |
| Unaccented queries give odd results | Diacritics, Unicode, and tokenizer mismatch | Test accent behavior; normalize in app |
| `đ` does not match `d` as expected | Inconsistent Unicode folding | Map `đ`/`Đ` explicitly if appropriate |
| `học máy` returns unrelated docs | Syllable splitting on multi-word terms | Segmentation, phrases, synonyms, ranking |
| Cross-tenant results leak | Missing tenant/auth filter | Enforce permission filter in query and search stage |
| Contains regex is slow | No efficient prefix index | Use anchored prefix or a search engine |
| User regex spikes CPU | Raw user input parsed as complex regex | Escape, rate-limit, cap length, index |
| Different fields need different analyzers | Classic text index limits | Use Search index custom mappings |
| Autocomplete returns noisy matches | Prefix too short or fuzziness too broad | Minimum length, ranking, tokenization |
| Newly added products missing in suggestions | Search index freshness lag | Monitor indexing lag and provide UX fallback |
| Creating second text index fails | One classic text index per collection | Combine into one compound text index |
| `$search` reports unsupported | Deployment lacks MongoDB Search | Check infrastructure, index, and server version |
| `$limit` before tenant filter yields too few hits | Global top K filtered afterward | Push tenant filter into search scope before limit |
| `nameNorm` differs between Java and JS | Divergent normalization logic | Share test cases and version the policy |
| Distinct SKUs confused by similar names | Fuzzy applied to exact IDs | Route exact lookups separately |

## 30. Exercises and Solutions

### Exercise 1. Pick the Right Tool

A user types `sam` and the UI wants to suggest `Samsung Galaxy A55` while typing. Is a classic text index on `name` sufficient?

**Answer:** No. `$text` matches whole tokens and does not generate prefixes. Use a normalized field + prefix index for start-of-name/brand suggestions, or MongoDB Search `autocomplete` for token-level suggestions and ranking.

### Exercise 2. Typo Matching

A text index holds the token `samsung`, and the user types `samsng`. Can you add `fuzzy: {maxEdits:1}` to `$text`?

**Answer:** No. `fuzzy` is not an option on classic `$text`. Use the MongoDB Search `text` operator with `fuzzy` on a supported deployment, or an external search engine.

### Exercise 3. Vietnamese `none`

Why is `default_language:"none"` better than forcing `english` on a Vietnamese product name collection? Does it recognize compound words?

**Answer:** `none` avoids applying mismatched English stemming and stop-word removal, but it **does not** provide Vietnamese word segmentation, synonyms, or fuzzy matching.

### Exercise 4. Normalizing `đ`

Does calling `normalize("NFD")` and stripping combining marks completely turn `điện thoại` into `dien thoai`?

**Answer:** No. `đ` is a distinct letter and must be mapped explicitly (`đ` → `d`, `Đ` → `D`) if that folding is desired, alongside lowercasing and whitespace normalization.

### Exercise 5. Which Query Benefits from a Prefix Index?

Given a B-tree index `{tenantId:1,nameNorm:1}` and a lowercased `nameNorm`:

```javascript
// A
{ tenantId: "shop-01", nameNorm: /^dien/ }

// B
{ tenantId: "shop-01", nameNorm: /dien/ }
```

**Answer:** Query A has an anchored literal prefix and is typically far more able to exploit the index efficiently than B. Verify with `explain` in your environment.

### Exercise 6. Prefix-of-Field vs. Prefix-of-Token

A product has `nameNorm: "dien thoai samsung galaxy a55"`. Why does the regex `/^sam/` fail to find it?

**Answer:** The string starts with `dien`, not `sam`. Mid-string prefix suggestions require a separate field/brand field, a token-prefix index, or a proper autocomplete index.

### Exercise 7. Fuzziness Does Not Solve Synonyms

A user enters `laptop`, while the document only contains `máy tính xách tay`. Why is `fuzzy maxEdits=1` not the right fix?

**Answer:** The two phrases differ completely in vocabulary and length—this is not a single-character typo. You need synonym mapping, query expansion, or semantic search.

### Exercise 8. Searching Multiple Words

Does:

```javascript
db.products.find({
  $text: { $search: "Samsung Galaxy" }
})
```

guarantee returning only documents containing the exact ordered phrase `Samsung Galaxy`?

**Answer:** No. Unquoted terms do not enforce ordered phrase AND semantics. Use phrase syntax or a search operator designed for that requirement.

### Exercise 9. One Text Index per Collection

A collection already has a text index on `name`. The team wants to create a second independent text index on `description`. Can they do this directly?

**Answer:** Not under classic text index rules. A collection allows only one classic text index, though it can index multiple fields with weights. If independent analyzers or index strategies are needed, evaluate MongoDB Search.

### Exercise 10. Cross-Tenant Suggestion Bug

A search index holds products from multiple tenants, and the API executes `$search` → `$limit: 10` → `$match: {tenantId:"shop-01"}`. What is wrong?

**Answer:** Limiting to the global top 10 can discard `shop-01` matches ranked past position 10; push tenant/permission filters into the search stage early with proper index mapping before taking top N, and still enforce authorization in the application tier.

### Exercise 11. Accent Stripping Loses Information

Why should you not store product names solely in unaccented form?

**Answer:** Unaccented text loses display fidelity and semantic distinctions: `bán`, `bàn`, and `bạn` all collapse to `ban`. Keep the original field and maintain a separate normalized field for search.

### Exercise 12. Features Missing from `$text`

Pick the two capabilities **unavailable** in classic `$text`: (A) `textScore`, (B) phrase search, (C) fuzzy edit distance, (D) autocomplete edge-grams.

**Answer:** C and D. A and B exist within classic text search (subject to language/tokenization limits).

### Exercise 13. Why Reindexing Is Needed After Changing Tokenizers

A team changes segmentation to treat `học máy` as a special single term, but updates only query-time normalization without updating existing documents/indexes. What goes wrong?

**Answer:** Index-time and query-time token representations diverge, hurting recall and distorting ranking. Maintain a consistent policy and run a controlled backfill/reindex whenever analyzers or segmentation rules change.

### Exercise 14. Matching Solution Complexity to Requirements

An internal app manages 20,000 equipment codes where users always search exact codes or code prefixes, with no fuzziness or Vietnamese needed. Should you immediately deploy MongoDB Search?

**Answer:** Not necessarily. B-tree equality and prefix queries verified with `explain` are likely sufficient. Pick the simplest tool that meets requirements.

### Exercise 15. Testing Typos and Precision

You enable `fuzzy maxEdits=2` and observe the zero-result rate drop. Can you conclude search quality improved?

**Answer:** Not yet. Broad fuzziness can flood results with false positives. Measure precision/recall@K, rank position of relevant hits, query latency, and suggestion UX across a representative typo dataset.

## 31. Vietnamese Search Design Checklist

When implementing:

1. **Classify queries:** exact ID/SKU, keyword, prefix, fuzzy, synonyms, or semantic.
2. **Preserve source data:** keep original names, accents, codes, and descriptions for display and reconciliation.
3. **Normalize Unicode:** enforce NFC, whitespace cleanup, and consistent casing rules.
4. **Decide accent folding:** whether to strip accents, how to handle `đ`, and how to boost accented hits.
5. **Handle compound words:** test multi-syllable words and domain phrases.
6. **Align index and query normalization:** identical algorithm and version, backed by unit tests.
7. **Do not force fuzziness into classic `$text`:** use a search engine or dedicated solution when edit distance is required.
8. **Do not force autocomplete into a text index:** use a prefix index or a proper autocomplete search index.
9. **Enforce tenant/permission scope:** apply filters before top-K and prevent data leakage.
10. **Design ranking:** exact > normalized/fuzzy where appropriate; consider brand, stock availability, and category.
11. **Guard query inputs:** trim, enforce min/max length, escape regexes, and rate-limit.
12. **Measure quality:** Vietnamese query set, recall/precision, typo recovery, and zero-result rate.
13. **Measure performance:** p95/p99 latency, index/storage overhead, concurrency, and search freshness.
14. **Verify infrastructure:** classic text index vs. MongoDB Search; never mix syntax between the two.
15. **Plan migration/reindex paths:** whenever adding normalized fields or changing analyzers, synonyms, or ranking.

## 32. Summary

**Classic MongoDB text indexes** provide basic keyword search supporting token matching, phrase/exclusion syntax, and `textScore`. However, they **do not natively support typo-tolerant fuzzy matching**, **do not generate autocomplete prefixes**, and **lack deep Vietnamese linguistic analysis**. These limitations are not bugs in `$text`—they reflect the boundary between a **text keyword index** and a **search engine**.

For Vietnamese, remember that **stripping accents is not understanding the language**: Unicode normalization, the letter `đ`, multi-syllable words, abbreviations, synonyms, and ranking policies all shape search quality. A practical path preserves **original fields**, adds **normalized fields**, uses **B-tree prefix indexes** for simple needs, and adopts **MongoDB Search / Atlas Search or an external search engine** when advanced autocomplete, fuzziness, or custom analyzers are required.

Ultimately, base architectural choices on **real user queries, tenant security, result quality, and latency**, rather than assuming creating a text index turns search into Google. Good search engineering matches the right mechanism to each query type, tests Vietnamese thoroughly, and continuously evaluates quality as data and needs evolve.

### MongoDB Documentation for Version Reference

- [MongoDB Manual — Text Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-text/)
- [MongoDB Manual — `$text` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/text/)
- [MongoDB Search — Overview](https://www.mongodb.com/docs/atlas/atlas-search/)
- [MongoDB Search — Fuzzy Matching](https://www.mongodb.com/docs/atlas/atlas-search/text/)
- [MongoDB Search — Autocomplete](https://www.mongodb.com/docs/atlas/atlas-search/autocomplete/)
