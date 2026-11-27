# Splitting Data Validation Between MongoDB and the Application

## 1. Why Validate Data Across Multiple Layers?

An application backed by MongoDB typically receives data from browsers, mobile apps, APIs, background jobs, import scripts, and other services. If each source sends data under different assumptions, inconsistent documents can end up in the collection:

```javascript
// All representing a course enrollment, yet with inconsistent types.
{ studentId: ObjectId("66a000000000000000000001"), status: "ACTIVE" }
{ studentId: "66a000000000000000000001", status: "active" }
{ studentId: null, status: "ACTVE" }
{ studentId: ObjectId("66a000000000000000000001"), status: 1 }
```

Every BSON document has a concrete structure, yet by default MongoDB allows documents in the same collection to carry different fields and types. That flexibility helps as models evolve; however, an application with stable business rules still needs critical fields to have the right types, appear when required, and obey data constraints.

For instance, a **course enrollment** feature has several distinct requirements:

- `studentId` and `courseId` must be valid `ObjectId`s.
- `status` accepts only specific values such as `PENDING`, `ACTIVE`, `CANCELLED`.
- A student cannot have two enrollment records for the same course under system rules.
- Only an authenticated student may enroll on their own behalf.
- Enrollment is allowed only while the course is open and has available seats.
- After cancellation, the status must not arbitrarily transition back to `ACTIVE` if policy requires re-enrolling.

These requirements belong to **different categories of checks**, so you should neither cram everything into one API function nor expect MongoDB's `$jsonSchema` to solve all of them alone.

This lesson divides responsibilities across **MongoDB schema validation**, **indexes**, **conditional write commands**, **transactions**, and **application-layer validation**. The goal is to block corrupted data at the storage layer while enforcing business logic accurately, returning clear errors to users, and maintaining consistency under concurrent requests.

## 2. Validation Layers in a System

A typical write path:

```text
Browser / mobile app / API client
             |
             v
  [1] Input UX validation (UI)
             |
             v
  [2] API / application layer
      - parse and normalize
      - authentication, authorization
      - business rules
      - state & reference checks
             |
             v
  [3] MongoDB write command
      - conditional filter / atomic update
      - transaction if modifying multiple documents
             |
             v
  [4] MongoDB
      - document validation / $jsonSchema
      - unique indexes and other indexes
      - atomicity, data persistence
             |
             v
  Document accepted or MongoDB returns error
```

Each layer has a distinct purpose:

| Layer | Primary Responsibility | Insufficient to Guarantee Alone |
| --- | --- | --- |
| **Client/UI** | Input guidance, fast feedback, pre-submit format checks | Data integrity: clients can be altered, bypassed, or spoofed |
| **API/application layer** | Parse input, normalize, authenticate/authorize, context-aware business rules, error messages | Stopping all bad data alone when scripts, workers, or other services write directly |
| **MongoDB schema validation** | Document shape, BSON types, required fields, allowed value sets, single-field bounds | Access control, document existence in other collections, and full workflows |
| **Unique index** | Uniqueness of a key or key combination under concurrent writes | Reference validity or valid state transitions |
| **Conditional update command** | Mutate only while document remains in expected state; single-document writes are atomic | Automatically coordinating changes across multiple documents |
| **Multi-document transaction** | Keep a group of writes across documents/collections all-or-nothing | Understanding business rules itself; the app must still build the right conditions |

**Design principle:** apply multiple layers for critical invariants, while maintaining **one consistent definition** of what the data means. For example, both the API and MongoDB must agree that `status` is `PENDING`, `ACTIVE`, or `CANCELLED`—never let each layer maintain a separate value list.

## 3. Classifying Rules by Nature

Before picking a tool, ask: "Can this rule be checked using a single document alone, or does it require external context?"

| Rule | Appropriate Location | Reason |
| --- | --- | --- |
| `studentId` required, BSON ObjectId type | MongoDB `$jsonSchema`; app also parses input | Invariant data structure across all write paths |
| `score` must be an integer from 0 to 100 | MongoDB `$jsonSchema`; app returns clear messages | Bound directly on a single field |
| `status` belongs to a fixed value set | MongoDB `enum`; app shares the same convention | Blocks invalid values across every write path |
| Email needs trimming and normalization per app policy | Application; MongoDB guards type/length | Normalization depends on policy and input handling |
| A student enrolls at most once per course | Compound unique index | Prevents duplicates even when two requests arrive concurrently |
| Logged-in user can only create their own enrollment | App/server authentication & authorization | Depends on request identity |
| Course must exist and still accept enrollments | App checks; conditional write/transaction under contention | Requires reading another collection and guarding consistency |
| Status transitions `PENDING → ACTIVE` only after payment | Application + conditional update | Depends on prior state and workflow outcome |
| Enrollment must decrement remaining seats together | Multi-document transaction or redesigned doc boundary | Multiple mutations must be atomic together |
| Display "You are already enrolled in this course" in English | Application/API | MongoDB returns technical errors; user-facing messaging belongs in the app |

Some rules can be enforced in more than one place. For instance, an age bound can be checked in the API for user feedback and in the schema to catch bugs in an import script. Repeating checks across two layers provides **defense in depth**, provided the rules and bounds stay aligned.

## 4. Practice Scenario: Course Enrollment Collection

Let's design the `enrollments_demo` collection with this sample document:

```javascript
{
  _id: ObjectId("66a000000000000000000010"),
  studentId: ObjectId("66a000000000000000000001"),
  courseId: ObjectId("66a000000000000000000002"),
  status: "PENDING",
  enrolledAt: ISODate("2026-11-14T01:30:00Z"),
  schemaVersion: NumberInt(1),
  score: NumberInt(80),
  runId: "row87-demo-001"
}
```

Field meanings:

- `studentId`: reference key to a student document.
- `courseId`: reference key to a course document.
- `status`: status within the business-defined value set.
- `enrolledAt`: enrollment timestamp, stored as BSON Date.
- `schemaVersion`: structural version understood by the application.
- `score`: optional field, integer 0–100.
- `runId`: practice run marker, solely for testing and controlled cleanup.

In this demo, each `studentId` + `courseId` pair has at most one record. This is a business assumption used to illustrate a unique index. If a student can retake the same course across multiple terms, a real model must add `offeringId`/`termId` or design a different uniqueness rule.

The `mongosh` examples below operate solely on the **`mongo_validation_lab`** database and a practice collection owned by the learner. In shared environments, never create or edit production collections without schema management authorization.

## 5. Protecting Structure in MongoDB with `$jsonSchema`

### 5.1. Creating a Collection with a Validator

Run in `mongosh` against a test database that does not yet contain a collection of the same name:

```javascript
const lab = db.getSiblingDB("mongo_validation_lab");

lab.createCollection("enrollments_demo", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "studentId",
        "courseId",
        "status",
        "enrolledAt",
        "schemaVersion"
      ],
      additionalProperties: false,
      properties: {
        _id: {
          bsonType: "objectId",
          description: "Document identifier"
        },
        studentId: {
          bsonType: "objectId",
          description: "Student must have an ObjectId"
        },
        courseId: {
          bsonType: "objectId",
          description: "Course must have an ObjectId"
        },
        status: {
          enum: ["PENDING", "ACTIVE", "CANCELLED"],
          description: "Valid enrollment status"
        },
        enrolledAt: {
          bsonType: "date",
          description: "Enrollment timestamp must be a BSON Date"
        },
        updatedAt: {
          bsonType: "date"
        },
        schemaVersion: {
          bsonType: "int",
          minimum: 1
        },
        score: {
          bsonType: "int",
          minimum: 0,
          maximum: 100
        },
        runId: {
          bsonType: "string",
          minLength: 1
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

Key details in this validator:

1. `bsonType: "object"` requires the document to be a BSON object.
2. `required` lists **the fields that must exist**. Listing a field in `properties` alone does not make it required.
3. `bsonType: "objectId"`, `"date"`, `"int"` distinguish actual BSON types, not just JSON display formatting.
4. `enum` limits `status` to the allowed values.
5. `minimum` and `maximum` bound `score`; `minLength` ensures `runId`, if present, is non-empty.
6. `additionalProperties: false` disallows fields outside `properties`. Since MongoDB adds `_id` automatically when needed, `_id` must be listed in `properties`. When adding new fields later, plan validator updates ahead of time.
7. `validationLevel: "strict"` checks every insert and document update against the validator; `validationAction: "error"` rejects invalid operations unless validation is explicitly bypassed where permitted.

This validator is a **structural contract**. It does not know whether `studentId` exists in a `students` collection, does not check remaining course capacity, and does not know who sent the request.

### 5.2. Why Must BSON Types Be Consistent?

In `mongosh`:

```javascript
NumberInt(80);                     // BSON Int32
NumberLong("80");                 // BSON Int64
ISODate("2026-11-14T01:30:00Z");  // BSON Date
ObjectId();                       // BSON ObjectId
```

A value that looks like "80" can be serialized into different BSON types depending on the driver and encoder. With `score: { bsonType: "int" }`, ensure the application genuinely writes a BSON Int32. For example, `NumberInt(80)` works in `mongosh`; in Node.js, use `Int32` from the `mongodb` package when specifying the exact type.

If legacy data uses `long` or another BSON numeric type, consider whether the schema should allow multiple numeric types or migrate existing data before applying the validator. Never widen types carelessly just to avoid errors without understanding the value domain.

### 5.3. Inserting a Valid Document

```javascript
const enrollments = lab.getCollection("enrollments_demo");
const studentId = new ObjectId();
const courseId = new ObjectId();
const runId = "row87-" + new ObjectId().toHexString();

const inserted = enrollments.insertOne({
  studentId: studentId,
  courseId: courseId,
  status: "PENDING",
  enrolledAt: new Date(),
  schemaVersion: NumberInt(1),
  score: NumberInt(80),
  runId: runId
});

printjson(inserted);
printjson(
  enrollments.findOne({ _id: inserted.insertedId, runId: runId })
);
```

On success, `insertOne` returns metadata such as `acknowledged` and `insertedId`. Here `studentId` and `courseId` are synthetic IDs; this step only verifies **document shape validity**. Ensuring those IDs match real student and course records remains a business-layer responsibility.

### 5.4. Rejected Data Examples

Suppose these operations are run individually after creating the collection with the validator:

```javascript
// Invalid: status is not in enum.
enrollments.insertOne({
  studentId: new ObjectId(),
  courseId: new ObjectId(),
  status: "WAITING_FOR_MAGIC",
  enrolledAt: new Date(),
  schemaVersion: NumberInt(1)
});

// Invalid: enrolledAt is a string instead of a BSON Date.
enrollments.insertOne({
  studentId: new ObjectId(),
  courseId: new ObjectId(),
  status: "PENDING",
  enrolledAt: "2026-11-14T01:30:00Z",
  schemaVersion: NumberInt(1)
});

// Invalid: missing courseId (required).
enrollments.insertOne({
  studentId: new ObjectId(),
  status: "PENDING",
  enrolledAt: new Date(),
  schemaVersion: NumberInt(1)
});
```

Each command is expected to fail validator checks; in MongoDB, document validation errors normally carry **code `121`** and an error name such as `DocumentValidationFailure`. Exact error payload structure varies by server and driver version. These examples are for observing behavior in a test environment; you do not need to run them repeatedly once the principle is clear.

**Note:** `required` and `bsonType` are two independent checks. A field present with `null` is invalid if the schema demands another type, such as `bsonType: "objectId"`. To allow `null`, express it explicitly in the schema.

### 5.5. Validators Also Apply to Updates

```javascript
// Valid: change score to an integer within range.
enrollments.updateOne(
  { _id: inserted.insertedId, runId: runId },
  { $set: { score: NumberInt(95), updatedAt: new Date() } }
);

// Invalid: score exceeds maximum.
enrollments.updateOne(
  { _id: inserted.insertedId, runId: runId },
  { $set: { score: NumberInt(150) } }
);

// Invalid: remove a required field.
enrollments.updateOne(
  { _id: inserted.insertedId, runId: runId },
  { $unset: { courseId: "" } }
);
```

With `strict` and `error`, MongoDB evaluates the **post-update document state**. If the resulting document violates the validator, the operation is rejected. That is a major strength of database-level validation: it does not depend on whether every API handler remembered to invoke the validation function.

## 6. What Must the Application Do Before Sending a Write Command?

### 6.1. Parse and Normalize Untrusted Input

A client might send:

```json
{
  "courseId": "66a000000000000000000002",
  "status": "ACTIVE",
  "score": 100,
  "studentId": "66a000000000000000000099"
}
```

Even though `courseId` is well-formed, the client **must not dictate** the logged-in account's `studentId`, `status`, `score`, or `enrolledAt`. Those fields must be set by the server according to permissions and business workflows.

An enrollment API might accept only:

```json
{
  "courseId": "66a000000000000000000002"
}
```

The application layer executes:

1. Authenticate the user from a verified session or token.
2. Read the user's `studentId` from trusted server auth context.
3. Validate `courseId` is a 24-hex-char ObjectId string and convert it to a BSON ObjectId.
4. Verify enrollment eligibility, open registration status, and business prerequisites.
5. Assign initial `status`, enrollment timestamp, and schema version on the server.
6. Send the normalized document to MongoDB.

### 6.2. Node.js Example: Validating Input and Building the Document

The following example uses the MongoDB Node.js driver. It is a sample service function called by an authenticated route/controller; `authContext` must come from authentication middleware, **never directly from the client request body**.

```javascript
import { ObjectId, Int32 } from "mongodb";

function parseObjectIdFromRequest(value, fieldName) {
  if (
    typeof value !== "string" ||
    !/^[0-9a-fA-F]{24}$/.test(value)
  ) {
    throw new Error(fieldName + " must be a 24-hex-character ObjectId");
  }
  return new ObjectId(value);
}

function buildEnrollmentDocument(body, authContext) {
  if (
    body === null ||
    typeof body !== "object" ||
    Array.isArray(body)
  ) {
    throw new Error("Body must be an object");
  }

  // Only accept input fields explicitly exposed by the API.
  const allowedKeys = new Set(["courseId"]);
  for (const key of Object.keys(body)) {
    if (!allowedKeys.has(key)) {
      throw new Error("Disallowed field: " + key);
    }
  }

  const courseId = parseObjectIdFromRequest(body.courseId, "courseId");

  // studentId was attached to context by auth middleware.
  const studentId = authContext?.studentId;
  if (!(studentId instanceof ObjectId)) {
    throw new Error("Missing authenticated student identity");
  }

  return {
    studentId,
    courseId,
    status: "PENDING",
    enrolledAt: new Date(),
    schemaVersion: new Int32(1)
  };
}

// Called inside a service/controller with db and authContext.
async function createEnrollment(db, body, authContext) {
  const candidate = buildEnrollmentDocument(body, authContext);

  // Business checks such as whether the course exists, allows enrollment,
  // and has seats remaining belong in the appropriate workflow.
  const result = await db
    .collection("enrollments_demo")
    .insertOne(candidate);

  return result.insertedId;
}
```

In this snippet, `Int32(1)` deliberately matches `bsonType: "int"`. Input data is converted into target storage types rather than writing raw client JSON straight to MongoDB. `createEnrollment` only demonstrates document construction and insertion; if business rules must protect course capacity against concurrency races, add the mechanisms from Section 8.

Production apps commonly use input validation libraries like JSON Schema validators, Zod, Joi, or framework-integrated validators. Regardless of the library, the core principles are **never trusting raw client bodies**, defining explicit contracts, and separating user input errors from system failures.

### 6.3. Business-Meaningful Validation

MongoDB knows `status` is in the allowed value set, yet it cannot know by itself:

- Is the student's account suspended?
- Is the course open for registration?
- Has the student completed prerequisite courses?
- Has the student paid or received approval?
- Which timezone governs the course registration deadline?
- Is an automated job permitted to change `status` from `PENDING` to `ACTIVE`?

These decisions rely on **context and policy**, so they belong in the business layer. Even if part of a rule could be crammed into a validator expression, never make the database depend on user identity or external service calls.

### 6.4. Normalizing Data Before Writing

Example account system accepting email addresses:

```javascript
function normalizeEmailForThisApp(input) {
  if (typeof input !== "string") {
    throw new Error("Email must be a string");
  }

  const result = input.trim().toLowerCase();
  if (!result || result.length > 254) {
    throw new Error("Email is invalid under application policy");
  }
  return result;
}
```

This illustrates a **simple normalization policy**, not a complete RFC/internationalized email validator. Lowercasing the entire address must be a consistent product decision. After normalization, the database can verify the field is a string within length bounds and enforce a unique index on the normalized value if required.

**Separate two concepts:** normalization transforms input into a canonical representation; validation decides whether data is accepted.

## 7. Guarantees Requiring Indexes or Conditional Writes, Not Just `$jsonSchema`

### 7.1. Uniqueness via Unique Indexes

The validator in Section 5 checks each document individually. It cannot stop two documents from having the same `studentId` and `courseId`. To enforce pair uniqueness:

```javascript
lab.enrollments_demo.createIndex(
  { studentId: 1, courseId: 1 },
  { unique: true, name: "uniq_student_course" }
);
```

If two requests insert the same pair concurrently, the database unique index blocks the duplicate write. The error typically carries code **`11000`** (`DuplicateKey`). The API should translate this into a domain message such as "Student is already enrolled in this course" rather than exposing raw index errors and internal details.

If the index is created after duplicate data already exists in the collection, index creation fails; duplicates must be resolved first.

**Hypothetical rule change example:** if a student can re-enroll in the same course across different offerings, a unique index on `studentId` + `courseId` becomes too restrictive. You must first update the business key (for instance, adding `offeringId`) before changing the index.

### 7.2. State Transitions Require Conditions on the Current Document

Suppose business rules only allow transitioning `PENDING` → `ACTIVE`. A race-prone pattern:

```javascript
// Unsafe under concurrency:
// 1. Read document and observe status = PENDING.
// 2. Another request cancels the enrollment.
// 3. First request still updates status to ACTIVE without re-checking.
```

Guard it directly in the write filter:

```javascript
const result = lab.enrollments_demo.updateOne(
  {
    _id: inserted.insertedId,
    status: "PENDING"
  },
  {
    $set: {
      status: "ACTIVE",
      updatedAt: new Date()
    }
  }
);

printjson(result);
```

If `matchedCount` is `0`, no document matched both `_id` and `status: "PENDING"`. The application checks why (missing, already cancelled, already active, etc.) and responds accordingly. Such an `updateOne` is **atomic at the single-document level**, reducing stale-state overwrite risks.

MongoDB's `enum` knows `ACTIVE` is a valid value, yet does not understand valid transitions between states. Thus **schema validation guards the target state**, while **conditional writes and the business layer guard state transitions**.

### 7.3. Cross-Collection References

Having valid ObjectIds for `studentId` and `courseId` does not guarantee matching documents exist. MongoDB does not create automatic foreign keys between `enrollments_demo.courseId` and `courses._id`.

The application layer should:

- Verify the course exists when accepting an enrollment.
- Define rules for what happens if a course is later deleted, hidden, or locked.
- Avoid automatically deleting valuable historical records.
- When strong cross-document consistency is required, use transactions or suitable synchronization mechanisms.

Simply "reading that the course exists" before inserting **still does not guarantee** the course stays present during the insert under concurrent deletes. Your required consistency guarantee dictates whether transactions and deletion policies are needed.

## 8. Protecting Multi-Document Invariants with Transactions

Consider a business invariant: enrolling a student into a course that has `seatsAvailable` seats left. Every new enrollment must:

1. Decrement `seatsAvailable` by exactly 1, provided seats remain and registration is open.
2. Create one new enrollment record without duplicating the student–course pair.

If decrementing succeeds and the insert fails—or vice versa—data becomes inconsistent. When this invariant is critical, the application can use a **multi-document transaction** on a supported MongoDB deployment.

Node.js service-layer example, assuming the `courses` collection has `_id`, `registrationOpen`, `seatsAvailable`, and the unique index exists on `enrollments_demo`:

```javascript
import { Int32 } from "mongodb";

async function reserveSeatAndEnroll(client, db, studentId, courseId) {
  const session = client.startSession();

  try {
    return await session.withTransaction(async () => {
      const courses = db.collection("courses");
      const enrollments = db.collection("enrollments_demo");

      // Condition and decrement run atomically on the course document.
      const seatUpdate = await courses.updateOne(
        {
          _id: courseId,
          registrationOpen: true,
          seatsAvailable: { $gt: 0 }
        },
        { $inc: { seatsAvailable: -1 } },
        { session }
      );

      if (seatUpdate.matchedCount !== 1) {
        throw new Error("COURSE_NOT_AVAILABLE");
      }

      // Unique index prevents two enrollments for the same student + course.
      const inserted = await enrollments.insertOne(
        {
          studentId,
          courseId,
          status: "PENDING",
          enrolledAt: new Date(),
          schemaVersion: new Int32(1)
        },
        { session }
      );

      return inserted.insertedId;
    });
  } finally {
    await session.endSession();
  }
}
```

Key takeaways:

- `$inc` with filter `seatsAvailable: { $gt: 0 }` protects seat decrements on a course document under concurrent requests.
- The unique index prevents duplicate student–course pairs.
- The transaction ensures both course and enrollment mutations commit together or roll back per transaction semantics.
- Authorization, prerequisites, student limits, and registration deadlines must still be checked by business logic.
- Transaction callbacks may be retried automatically by the driver on transient errors; **never place irreversible external side effects** like sending emails or charging payments directly inside the callback without idempotency/outbox design.
- Transactions require an appropriate MongoDB topology such as a replica set or sharded cluster; never assume a standalone test `mongod` behaves identically.

This exemplifies **separation of concerns**: the application decides *when* enrollment is allowed; conditional updates guard seat count; unique indexes prevent duplicates; the validator enforces document shape; and transactions protect the multi-document change set.

## 9. Validating Partial Updates (PATCH)

Update APIs rarely resend the entire document. Example request:

```json
{
  "status": "ACTIVE"
}
```

The application must verify **which fields are mutable**, who is authorized to change them, the current state, and transition rules. Never do this:

```javascript
// Unsafe pattern illustration:
// await collection.updateOne({ _id }, { $set: req.body });
```

The request could contain `studentId`, `courseId`, `score`, or `schemaVersion`; blindly applying `req.body` lets clients overwrite server-managed fields. You must also guard against disallowed field names and unexpected update operators or shapes.

Instead, define explicit business operations, such as "activate enrollment":

```javascript
async function activateEnrollment(enrollments, enrollmentId) {
  const result = await enrollments.updateOne(
    { _id: enrollmentId, status: "PENDING" },
    {
      $set: {
        status: "ACTIVE",
        updatedAt: new Date()
      }
    }
  );

  if (result.matchedCount === 0) {
    throw new Error("ENROLLMENT_NOT_PENDING");
  }

  return result.modifiedCount;
}
```

This function assumes **authentication, authorization, and activation eligibility** were already verified by the caller. In a real API, never let arbitrary users activate arbitrary enrollments. MongoDB validates the post-update document schema, yet the validator cannot check whether the actor is authorized to perform that action.

**Apply field ownership:** designate which fields are client-supplied, which are system-generated, and which are restricted to administrative workflows. This is a straightforward defense against *mass assignment* vulnerabilities.

## 10. MongoDB Validation Modes

MongoDB lets you adjust **enforcement scope** and **violation action**, which helps when introducing validators to existing collections.

### 10.1. `validationLevel`

| Value | Core Meaning |
| --- | --- |
| `strict` | Checks all inserts and updates against the validator, unless bypassed where permitted |
| `moderate` | Checks inserts and updates to currently valid documents; skips enforcing the validator on updates to already-invalid legacy documents |
| `off` | Disables collection document validation |

Note on `moderate`: it does not mean "check only a few fields" or "allow inserting bad data." It helps during transitional phases when legacy data cannot all be fixed at once, yet never replaces a data cleanup plan.

### 10.2. `validationAction`

| Value | Typical Behavior |
| --- | --- |
| `error` | Rejects operations violating the validator |
| `warn` | Permits the operation and logs validation warnings to the server log |

Some MongoDB versions add extended logging options or actions. When targeting a specific server version, use the options supported by that version. `error` and `warn` capture the fundamental distinction between **blocking** and **observing**.

Example toggling action on the **demo collection** once you understand the impact:

```javascript
lab.runCommand({
  collMod: "enrollments_demo",
  validationAction: "warn"
});

// After normalizing data and ready to enforce strictly:
lab.runCommand({
  collMod: "enrollments_demo",
  validationLevel: "strict",
  validationAction: "error"
});
```

`collMod` alters the existing collection's configuration; on shared collections, follow your project's schema change process. With `validationAction: "warn"`, bad data still enters the collection; a warning **does not mean the record was fixed**. Moreover, unique indexes still reject duplicates even when schema validation is in `warn` mode.

### 10.3. Inspecting a Collection's Validator Configuration

In `mongosh`:

```javascript
printjson(lab.getCollectionInfos({ name: "enrollments_demo" }));
```

Collection metadata shows `options.validator`, `validationLevel`, and `validationAction`. Reading metadata may require appropriate privileges for your account.

**Special case:** write operations passing `bypassDocumentValidation`, when executed by an authorized account, skip schema validation. That is why a database validator is an important protection layer, yet never the sole security boundary. Grant and use bypass privileges only under controlled operational procedures.

## 11. Coordinating Schema Validation While Data Evolves

### 11.1. Real-World Challenges When Updating a Schema

Suppose v1 stored:

```javascript
{
  studentId: ObjectId("66a000000000000000000001"),
  courseId: ObjectId("66a000000000000000000002"),
  status: "PENDING"
}
```

v2 adds required `enrolledAt` and `schemaVersion`. Enabling a `strict`/`error` validator immediately while legacy records lack those fields causes future updates on old documents to fail. Older app instances still running during a rolling deploy may also keep sending the old shape and fail.

Treat schema changes as **contract changes between stored data and application versions**.

### 11.2. Phased Transition Process

A practical sequence:

1. **Define the target:** which fields are added, removed, or retyped; which invariants are mandatory; and which API versions are impacted.
2. **Audit existing data:** count documents missing fields or holding wrong types; identify all writers (APIs, jobs, ETL).
3. **Deploy compatible software:** new code handles both old and new shapes during the transition window; new writers emit full data.
4. **Observe violations:** consider `warn` mode to measure bad write rates in a suitable environment alongside application error reporting.
5. **Backfill legacy data:** update documents in conditional batches; store checkpoints and ensure safe recovery if interrupted.
6. **Enable strict enforcement:** once all writers are compatible and data is remediated, apply `strict` + `error` through your release process.
7. **Monitor post-release:** watch validation error codes, duplicate keys, and related metrics so users do not hit cryptic errors.

MongoDB does not automatically make existing data valid just because a validator was added. Attaching a validator to an existing collection primarily governs subsequent writes per the chosen `validationLevel` and `validationAction`.

### 11.3. Choosing Strict vs. Flexible for New Fields

`additionalProperties: false` creates a closed schema: only declared fields may be written. It works well when strict data contracts and synchronized releases are required.

However, when multiple app versions share one collection, an overly closed schema can break rollouts adding a new field if the validator is not updated first. Deciding whether to permit extra fields is a deliberate design choice. Either way, the API must still restrict which fields clients are allowed to supply.

**Separate responsibilities:** MongoDB decides whether a document complies with the storage contract; the application decides whether a request is valid in the **context of version, user, and business rules**.

## 12. Returning Helpful Errors from MongoDB to the API

A well-designed API never forwards raw driver exceptions verbatim to clients. It maps errors into meaningful responses while preserving technical details in internal logs.

| Error Source | Example | Typical API Response |
| --- | --- | --- |
| API input check | `courseId` is not a valid ObjectId string | HTTP `400 Bad Request` with field details |
| Authentication | Not logged in or invalid token | `401 Unauthorized` |
| Authorization | Not allowed to enroll on someone else's behalf | `403 Forbidden` |
| Business state | Course registration is closed | `409 Conflict` or appropriate business code |
| Unique index (`11000`) | Student–course pair already exists | `409 Conflict`, message without internal index details |
| Document validation (`121`) | Server received wrong BSON type / missing required / bad enum | Handle as contract mismatch or bad input; log for investigation |
| Network, timeout, server failure | Cannot reach MongoDB | Appropriate system error response, detailed internal logs, and sensible retries |

The HTTP codes above are standard mappings and can be adapted to your project's API contract. Notably, if the app already validated input yet still encounters code `121`, that often signals **schema drift between app and database** or a non-conforming writer—do not blindly tell the user they entered invalid input.

Node.js service-layer error handling example:

```javascript
try {
  const result = await enrollments.insertOne(candidate);
  return { id: result.insertedId.toHexString() };
} catch (err) {
  if (err?.code === 11000) {
    throw new Error("ENROLLMENT_ALREADY_EXISTS");
  }
  if (err?.code === 121) {
    // Log technical details internally; check schema or data drift.
    throw new Error("INVALID_STORED_DOCUMENT_SHAPE");
  }
  throw err;
}
```

This snippet demonstrates **error classification in the service layer**; the controller maps internal error codes to the agreed HTTP responses. Never expose stack traces, raw documents, connection strings, or sensitive schema internals directly to clients.

### 12.1. Logging Errors with Safe Context

Application write logs should capture safe, actionable context such as:

- request ID or correlation ID to trace a flow end to end;
- business operation name, collection name, and application version;
- MongoDB error code and violated constraint category;
- timestamp and retry outcome if applicable;
- blast radius (a single request vs. widespread failures after a deploy).

Never log secrets, passwords, tokens, unnecessary personal data, or full sensitive documents just to debug a validation error.

## 13. Why Not Validate Only in the App or Only in the Database?

### 13.1. If Validating Only in the Application

Suppose the main API has `validateEnrollment()`, yet an import script writes straight to MongoDB:

```text
API request --> validateEnrollment() --> MongoDB

Import job -----------------------> MongoDB
```

If the import job skips that library or has a bug, bad data still enters the collection. With a database document validator, core type and required-field contracts are enforced across **all standard writers**, whether from an API or a batch job.

### 13.2. If Validating Only in the Database

MongoDB can reject `score = 150`, yet cannot know whether the caller is permitted to grade, whether the student is eligible, or whether the workflow allows the state transition. Database errors are also hard to translate directly into localized, form-specific UI messages.

Pushing all business logic into a validator layer tightly couples application policy to storage and becomes unwieldy. MongoDB document validation belongs on **storage structure integrity**, whereas business services belong on **context-driven decisions**.

### 13.3. When Multiple Services Write to One Collection

Every writer must follow a shared contract covering ID types, field names, enums, and date conventions. MongoDB's validator acts as the shared safety net, while each service still performs checks tailored to its responsibility.

If multiple services mutate `status`, designate **one service owning the state machine** or a shared API/command rather than letting each service interpret state transitions independently. State-filtered conditional updates protect against concurrency races, yet a unified policy in the business layer is still essential.

## 14. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Better Approach |
| --- | --- | --- |
| Assuming client validation is secure enough | Forged requests or bypassed UI | Validate and authorize independently in the API |
| Using only `$jsonSchema` for uniqueness | Individually valid docs can duplicate business keys | Create a unique index on the right key |
| Checking only that `courseId` is 24 hex chars | Valid format, yet course might not exist | Check references and business lifecycle |
| Reading state then updating unconditionally | Concurrent requests can overwrite transitions | Filter updates by expected state/version |
| Updating two collections without coordination | Enrollment created without decrementing seats or vice versa | Use transactions or redesign document boundaries |
| Writing raw `req.body` into `$set` | Clients can alter internal or restricted fields | Use explicit allowlists and business commands |
| Using generic JS Number when validator expects `int` | Frequent BSON type errors | Enforce consistent driver types and serialization |
| Turning on `strict`/`error` before old data conforms | Legacy writers and updates to old docs get rejected | Audit, expand schema, backfill, and roll out in phases |
| Leaving `warn` on forever and treating it as protection | Bad data keeps getting saved | Monitor warnings and switch to blocking when ready |
| Granting app accounts unrestricted bypass rights | Disables database-level protection | Restrict bypass privileges and govern usage |
| Returning raw MongoDB errors to the API | Leaks internals; hard for users to act on | Map errors cleanly and log internally |
| Copying enum definitions without syncing | API accepts values DB rejects, or vice versa | Maintain one versioned contract source of truth |

## 15. Hands-On Observation of Split Responsibilities

The steps below continue using the `lab`, `enrollments`, `inserted`, and `runId` variables created in `mongosh` in Section 5.

### 15.1. Testing Structural Rules

1. Use `findOne` to read the valid document created earlier.
2. Try updating `score` to `NumberInt(150)` and observe the validation error.
3. Read the document back to confirm the invalid operation left it unchanged.
4. Try updating `score` to `NumberInt(95)` and observe the valid update succeed.

Before-and-after read example:

```javascript
const exactFilter = {
  _id: inserted.insertedId,
  runId: runId
};

printjson(
  enrollments.findOne(
    exactFilter,
    { score: 1, status: 1, schemaVersion: 1 }
  )
);
```

### 15.2. Testing Uniqueness

If you created the unique index from Section 7, a second record sharing the same `studentId` and `courseId` violates the index even when all other fields are schema-valid:

```javascript
// Expected duplicate key error if this pair already exists.
enrollments.insertOne({
  studentId: studentId,
  courseId: courseId,
  status: "PENDING",
  enrolledAt: new Date(),
  schemaVersion: NumberInt(1),
  runId: runId
});
```

Distinguish the outcomes:

- `score` out of bounds: violates the **document validator**.
- Duplicate `studentId` + `courseId` pair: violates the **unique index**.
- Course registration closed: **business rule**, must be checked and enforced appropriately.
- User enrolling on someone else's behalf: **authorization rule**, must be blocked in the API/service.

### 15.3. Cleaning Up the Practice Document

Because the demo uses a dedicated `runId`, verify the exact database, collection, and document before deleting:

```javascript
print("database=" + lab.getName());
print("collection=" + enrollments.getName());
print("runId=" + runId);
printjson(enrollments.findOne(exactFilter));
```

Only after confirming it matches the document you created:

```javascript
const deletion = enrollments.deleteOne(exactFilter);
printjson(deletion);
print("remaining=" + enrollments.countDocuments(exactFilter));
```

Normally `deletedCount` is `1` and `remaining` is `0`. Never drop the whole database or collection to clean up a single run; the validator, indexes, and collection may be shared with others in a shared lab environment.

## 16. Decision Table for Real Projects

When taking on a new requirement, start with this decision matrix:

| Question | If the Answer Is "Yes" | Mechanism to Consider |
| --- | --- | --- |
| Does the rule depend only on one document's fields/types? | Can apply uniformly across all writers | MongoDB `$jsonSchema` |
| Does the user need immediate feedback while typing/submitting? | Can validate early | UI validation and API input validation |
| Does the rule depend on who is making the request? | Requires identity/permissions | API, service, auth middleware |
| Need to normalize strings, cast from JSON, or set system fields? | Must construct a contract-compliant document | Application layer |
| Need to prevent duplicates under concurrent requests? | Unique key constraint exists | Unique index |
| Must update only while prior value matches expectation? | Concurrency race risk exists | Conditional filter, atomic update, versioning |
| Must multiple documents change together? | Cross-document invariant exists | Transaction or data model redesign |
| Must the schema evolve while legacy data exists? | Multiple writers/versions coexist | Migration, `collMod`, observation, phased rollout |
| Must database errors become clean API responses? | Clients should not see raw DB errors | Error mapping, structured logging |

**Core mindset to keep:** the application is responsible for understanding **who is acting, whether they are authorized, and whether business rules are met**. MongoDB is responsible for protecting the **shape and foundational integrity of stored data**; unique indexes, conditional updates, and transactions provide guarantees that `$jsonSchema` alone cannot. Together, both sides keep data clean even with many clients, multiple writers, and concurrent requests.
